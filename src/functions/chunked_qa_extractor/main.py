import json
import boto3
import os
from decimal import Decimal


def handler(event, context):
    """
    Extract Q&A pairs from interview transcript chunks using Claude 3.5 Haiku.
    Fast and cost-effective processing for structured data extraction.
    """
    
    bedrock = boto3.client('bedrock-runtime')
    dynamodb = boto3.resource('dynamodb')
    
    # Get chunk data from the event (passed by Step Functions Map)
    chunk_index = event['id']  # This is actually the chunk_index
    interview_id = event['interview_id']
    position = event['position']
    
    # Construct the proper DynamoDB key (composite key format)
    chunk_id = f"{interview_id}#{chunk_index}"
    
    try:
        # Get the full chunk data from DynamoDB
        chunk_table = dynamodb.Table('interview_chunks')
        chunk_response = chunk_table.get_item(Key={'id': chunk_id})
        
        if 'Item' not in chunk_response:
            raise Exception(f"Chunk not found in DynamoDB: {chunk_id}")
        
        chunk_data = chunk_response['Item']
        print(f"Processing chunk {chunk_index} for interview {interview_id}")
        
        # Extract Q&A pairs from this chunk
        qa_pairs = extract_qa_from_chunk(bedrock, chunk_data)
        
        # Save extracted Q&A pairs to DynamoDB
        qa_table = dynamodb.Table('interview_qa')
        
        saved_count = 0
        for qa in qa_pairs:
            # Create unique ID for each Q&A pair
            qa_id = f"{chunk_data['interview_id']}#qa#{chunk_data['chunk_index']}#{qa['index']}"
            
            qa_item = {
                'id': qa_id,
                'interview_id': chunk_data['interview_id'],
                'position': chunk_data['position'],
                'chunk_index': chunk_data['chunk_index'],
                'qa_index': qa['index'],
                'global_qa_index': None,  # Will be set during merge phase
                'question_text': qa['q_text'],
                'answer_text': qa['a_text'],
                'answer_start_ms': Decimal(str(qa['a_start_ms'])),
                'answer_end_ms': Decimal(str(qa['a_end_ms'])),
                'answer_duration_ms': Decimal(str(qa['a_end_ms'] - qa['a_start_ms'])),
                'chunk_text_used': chunk_data['text'][:500] + '...',  # Store excerpt for debugging
                'processing_status': 'extracted',
                'extraction_confidence': qa.get('confidence', 'unknown')
            }
            
            qa_table.put_item(Item=qa_item)
            saved_count += 1
        
        # Update chunk processing status
        chunk_table = dynamodb.Table('interview_chunks')
        chunk_table.update_item(
            Key={'id': chunk_id},
            UpdateExpression='SET processing_status = :status, qa_count = :count',
            ExpressionAttributeValues={
                ':status': 'qa_extracted',
                ':count': saved_count
            }
        )
        
        return {
            'statusCode': 200,
            'chunk_id': chunk_id,
            'qa_pairs_extracted': saved_count,
            'chunk_index': chunk_data['chunk_index'],
            'interview_id': chunk_data['interview_id']
        }
        
    except Exception as e:
        print(f"Error extracting Q&A from chunk {chunk_id}: {str(e)}")
        
        # Update chunk with error status
        chunk_table = dynamodb.Table('interview_chunks')
        chunk_table.update_item(
            Key={'id': chunk_id},
            UpdateExpression='SET processing_status = :status, error_message = :error',
            ExpressionAttributeValues={
                ':status': 'extraction_failed',
                ':error': str(e)
            }
        )
        raise


def extract_qa_from_chunk(bedrock_client, chunk_data):
    """
    Use Claude 3.5 Haiku to extract structured Q&A pairs from a transcript chunk.
    """
    
    # Get the inference profile ARN from environment variables
    inference_profile_arn = os.environ.get('BEDROCK_INFERENCE_PROFILE_ARN')
    if not inference_profile_arn:
        # Fallback to direct model ID (though this may not work in all cases)
        model_id = "anthropic.claude-3-5-haiku-20241022-v1:0"
    else:
        model_id = inference_profile_arn
    
    # Build the extraction prompt
    system_prompt = """You are an expert at extracting structured Q&A data from interview transcripts. 
You must return ONLY valid JSON with no additional text or explanation."""
    
    user_prompt = f"""You'll receive a transcript segment with speakers and timestamps. 
Return ONLY valid JSON in this exact format:
{{
  "qa": [
    {{
      "index": 0,
      "q_text": "Question text from interviewer",
      "a_text": "Complete answer text from candidate", 
      "a_start_ms": 123000,
      "a_end_ms": 456000,
      "confidence": "high"
    }}
  ]
}}

CRITICAL RULES:
- "question" = interviewer utterances that ask something
- "answer" = candidate utterances that respond to questions
- Merge multi-turn answers by the candidate until interviewer speaks again
- Use timestamps from the transcript (convert [MM:SS] to milliseconds)
- If a question or answer is incomplete in this chunk, omit it completely
- confidence: "high" if Q&A is complete, "medium" if partial, "low" if unclear
- Return empty array if no complete Q&A pairs found

Transcript segment:
{chunk_data['text']}"""

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4000,
        "temperature": 0.1,  # Low temperature for consistent structured output
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": user_prompt
            }
        ]
    }
    
    try:
        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=json.dumps(request_body),
            contentType='application/json',
            accept='application/json'
        )
        
        response_body = json.loads(response['body'].read())
        content_text = response_body['content'][0]['text']
        
        # Parse JSON response
        try:
            qa_data = json.loads(content_text)
            return qa_data.get('qa', [])
            
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON response: {content_text}")
            print(f"JSON Error: {str(e)}")
            
            # Try to extract JSON from text if wrapped in other content
            content_text = content_text.strip()
            if content_text.startswith('```json'):
                content_text = content_text[7:-3].strip()
            elif content_text.startswith('```'):
                content_text = content_text[3:-3].strip()
            
            try:
                qa_data = json.loads(content_text)
                return qa_data.get('qa', [])
            except json.JSONDecodeError:
                print(f"Still failed to parse after cleanup: {content_text}")
                return []
        
    except Exception as e:
        print(f"Error calling Bedrock for Q&A extraction: {str(e)}")
        return []


def convert_timestamp_to_ms(timestamp_str):
    """
    Convert [MM:SS] timestamp to milliseconds.
    """
    
    try:
        # Remove brackets and split
        time_part = timestamp_str.strip('[]')
        parts = time_part.split(':')
        
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = int(parts[1])
            return (minutes * 60 + seconds) * 1000
        else:
            return 0
    except (ValueError, IndexError):
        return 0
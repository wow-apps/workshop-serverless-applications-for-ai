import json
import boto3
import uuid
import os
from datetime import datetime


def handler(event, context):
    """
    Extract Q&A pairs from interview transcript using Bedrock Claude 4 Sonnet.
    Single-pass processing for complete interviews (up to 200k context).

    Input event should contain:
    - interview_id: UUID of the interview
    """

    dynamodb = boto3.resource('dynamodb')
    bedrock = boto3.client('bedrock-runtime')

    interview_id = event['interview_id']

    try:
        # Step 1: Get transcript from DynamoDB
        transcriptions_table = dynamodb.Table('interview_transcriptions')
        response = transcriptions_table.get_item(Key={'id': interview_id})

        if 'Item' not in response:
            raise Exception(
                f"Interview transcript not found for ID: {interview_id}")

        interview_data = response['Item']
        transcript = interview_data['interview_transcript']

        # Step 2: Extract Q&A pairs using Bedrock Claude 4 Sonnet
        qa_pairs = extract_qa_pairs(bedrock, transcript, interview_data.get('position_description', ''))

        # Step 3: Save Q&A pairs to DynamoDB
        qa_table = dynamodb.Table('interview_qa')
        saved_pairs = []

        for index, qa_pair in enumerate(qa_pairs):
            qa_id = str(uuid.uuid4())

            item = {
                'id': qa_id,
                'interview_id': interview_id,
                'position_name': interview_data['position_name'],
                'index': index,
                'question': qa_pair['question'],
                'answer': qa_pair['answer'],
                'question_type': qa_pair.get('question_type', 'other'),
                'answer_quality': qa_pair.get('answer_quality', 'unclear'),
                'processing_status': 'extracted',
                'created_at': datetime.utcnow().isoformat()
            }

            qa_table.put_item(Item=item)
            saved_pairs.append(item)

        return {
            'statusCode': 200,
            'interview_id': interview_id,
            'qa_pairs_extracted': len(saved_pairs),
            'qa_pairs': saved_pairs
        }

    except Exception as e:
        print(f"Error extracting Q&A pairs: {str(e)}")
        raise


def extract_qa_pairs(bedrock_client, transcript, position_description):
    """
    Use Bedrock Claude 4 Sonnet to extract Q&A pairs from transcript.
    Single-pass processing with full context understanding.
    """

    system_prompt = """You are an expert at analyzing job interviews and extracting structured Q&A pairs. 
You must return ONLY valid JSON with no additional text or explanation."""

    user_prompt = f"""Analyze this English interview transcript and extract all question-answer pairs.

Position Context:
{position_description}

Transcript contains dialogue between an Interviewer and a Candidate.

Return ONLY valid JSON in this exact format:
{{
  "qa_pairs": [
    {{
      "index": 0,
      "question": "Complete question text from interviewer",
      "answer": "Complete answer text from candidate",
      "question_type": "technical|behavioral|experience|other",
      "answer_quality": "detailed|brief|unclear"
    }}
  ]
}}

Rules:
1. Extract complete question-answer pairs only
2. Questions from Interviewer, answers from Candidate  
3. Combine multi-turn responses by same speaker
4. Skip small talk, focus on substantial Q&A
5. Classify question types and answer quality
6. Preserve original English text
7. Return empty array if no valid pairs found

Transcript:
{transcript}"""

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 8000,  # Increased for longer responses
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
        # Get the inference profile ARN from environment variables
        inference_profile_arn = os.environ.get('BEDROCK_INFERENCE_PROFILE_ARN')
        if not inference_profile_arn:
            raise Exception("BEDROCK_INFERENCE_PROFILE_ARN environment variable not set")

        response = bedrock_client.invoke_model(
            modelId=inference_profile_arn,
            body=json.dumps(request_body),
            contentType='application/json',
            accept='application/json'
        )

        response_body = json.loads(response['body'].read())
        content = response_body['content'][0]['text']

        # Parse the JSON response
        try:
            qa_data = json.loads(content.strip())
            qa_pairs = qa_data.get('qa_pairs', [])
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON response: {content}")
            print(f"JSON Error: {str(e)}")
            
            # Try to extract JSON from text if wrapped in other content
            content_clean = content.strip()
            if content_clean.startswith('```json'):
                content_clean = content_clean[7:-3].strip()
            elif content_clean.startswith('```'):
                content_clean = content_clean[3:-3].strip()
            
            try:
                qa_data = json.loads(content_clean)
                qa_pairs = qa_data.get('qa_pairs', [])
            except json.JSONDecodeError:
                print(f"Still failed to parse after cleanup: {content_clean}")
                return []

        # Validate the response format
        if not isinstance(qa_pairs, list):
            print(f"Bedrock response qa_pairs is not a list: {type(qa_pairs)}")
            return []

        validated_pairs = []
        for pair in qa_pairs:
            if (isinstance(pair, dict) and
                    'question' in pair and 'answer' in pair):
                validated_pairs.append({
                    'question': pair['question'],
                    'answer': pair['answer'],
                    'question_type': pair.get('question_type', 'other'),
                    'answer_quality': pair.get('answer_quality', 'unclear')
                })
            else:
                print(f"Skipping invalid Q&A pair: {pair}")

        return validated_pairs

    except json.JSONDecodeError as e:
        print(f"Failed to parse Bedrock response as JSON: {str(e)}")
        print(f"Raw response: {content}")
        raise Exception("Bedrock returned invalid JSON")

    except Exception as e:
        print(f"Error calling Bedrock: {str(e)}")
        raise

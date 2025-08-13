import json
import boto3
import uuid
from datetime import datetime


def handler(event, context):
    """
    Extract Q&A pairs from interview transcript using Bedrock Claude Haiku 3.5.

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

        # Step 2: Extract Q&A pairs using Bedrock Claude Haiku 3.5
        qa_pairs = extract_qa_pairs(bedrock, transcript)

        # Step 3: Save Q&A pairs to DynamoDB
        qa_table = dynamodb.Table('interview_qa')
        saved_pairs = []

        for index, qa_pair in enumerate(qa_pairs):
            qa_id = str(uuid.uuid4())

            item = {
                'id': qa_id,
                'interview_id': interview_id,
                'index': index,
                'question': qa_pair['question'],
                'answer': qa_pair['answer'],
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


def extract_qa_pairs(bedrock_client, transcript):
    """
    Use Bedrock Claude Haiku 3.5 to extract Q&A pairs from transcript.
    """

    prompt = f"""
    Please analyze the following interview transcript and extract all question-answer pairs. 
    
    The transcript contains dialogue between an Interviewer and a Candidate, marked with "Interviewer:" and "Candidate:" prefixes.
    
    Extract each question asked by the interviewer and the corresponding answer given by the candidate.
    
    Return the result as a JSON array where each object has "question" and "answer" fields.
    
    Rules:
    1. Only extract complete question-answer pairs
    2. Questions should be from the Interviewer
    3. Answers should be from the Candidate
    4. Combine multiple consecutive statements from the same speaker into one question or answer
    5. Skip small talk, introductions, and closing remarks
    6. Focus on technical questions and substantial answers
    
    Transcript:
    {transcript}
    
    Return only the JSON array, no additional text or explanation.
    """

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4000,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    try:
        response = bedrock_client.invoke_model(
            modelId='anthropic.claude-3-5-haiku-20241022-v1:0',
            body=json.dumps(request_body),
            contentType='application/json',
            accept='application/json'
        )

        response_body = json.loads(response['body'].read())
        content = response_body['content'][0]['text']

        # Parse the JSON response
        qa_pairs = json.loads(content.strip())

        # Validate the response format
        if not isinstance(qa_pairs, list):
            raise Exception("Bedrock response is not a JSON array")

        for pair in qa_pairs:
            if (not isinstance(pair, dict) or 
                'question' not in pair or 'answer' not in pair):
                raise Exception("Invalid Q&A pair format in Bedrock response")

        return qa_pairs

    except json.JSONDecodeError as e:
        print(f"Failed to parse Bedrock response as JSON: {str(e)}")
        print(f"Raw response: {content}")
        raise Exception("Bedrock returned invalid JSON")

    except Exception as e:
        print(f"Error calling Bedrock: {str(e)}")
        raise

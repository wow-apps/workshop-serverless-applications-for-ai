import json
import boto3
import os
import time
import random
from decimal import Decimal
from botocore.exceptions import ClientError


def handler(event, context):
    """
    Process DynamoDB stream events from interview_qa table.
    Score answers against vacancy requirements using Claude 4 Sonnet.

    Triggered when new Q&A pairs are inserted into the interview_qa table.
    """

    dynamodb = boto3.resource('dynamodb')
    bedrock = boto3.client('bedrock-runtime')

    processed_records = 0

    for record in event['Records']:
        try:
            # Only process INSERT events (new Q&A pairs)
            if record['eventName'] != 'INSERT':
                continue

            # Extract Q&A data from DynamoDB stream record
            qa_data = record['dynamodb']['NewImage']

            qa_id = qa_data['id']['S']
            interview_id = qa_data['interview_id']['S']
            question = qa_data['question']['S']
            answer = qa_data['answer']['S']

            print(f"Processing Q&A scoring for: {qa_id}")

            # Skip if already scored (has answer_score)
            if 'answer_score' in qa_data:
                print(f"Q&A {qa_id} already scored, skipping")
                continue

            # Get vacancy requirements from interview_transcriptions table
            position_description = get_position_description(
                dynamodb, interview_id)

            # Score the answer using Claude 4 Sonnet
            score_result = score_answer(
                bedrock, question, answer, position_description)

            # Update the Q&A record with score and summary
            update_qa_with_score(dynamodb, qa_id, score_result)

            processed_records += 1
            print(
                f"Successfully scored Q&A {qa_id}: {score_result['score']}/10")

        except Exception as e:
            print(
                f"Error processing record {record.get('dynamodb', {}).get('Keys', {})}: {str(e)}")
            # Continue processing other records even if one fails
            continue

    return {
        'statusCode': 200,
        'processed_records': processed_records
    }


def get_position_description(dynamodb, interview_id):
    """
    Get the position description from interview_transcriptions table.
    """
    try:
        table = dynamodb.Table('interview_transcriptions')
        response = table.get_item(Key={'id': interview_id})

        if 'Item' not in response:
            print(f"Interview {interview_id} not found, using default")
            return "No specific position requirements available"

        return response['Item'].get(
            'position_description',
            'No specific position requirements available')

    except Exception as e:
        print(f"Error getting position description: {str(e)}")
        return "No specific position requirements available"


def score_answer(bedrock_client, question, answer, position_description):
    """
    Use Claude 4 Sonnet to score an interview answer against vacancy requirements.
    Includes retry logic for throttling.
    """

    # Get the inference profile ARN from environment variables
    inference_profile_arn = os.environ.get('BEDROCK_INFERENCE_PROFILE_ARN')
    if not inference_profile_arn:
        raise Exception(
            "BEDROCK_INFERENCE_PROFILE_ARN environment variable not set")

    system_prompt = """You are an expert technical interviewer and hiring manager.
You must evaluate interview answers against job requirements and return ONLY valid JSON."""

    user_prompt = f"""Evaluate this interview answer against the job requirements.

POSITION REQUIREMENTS:
{position_description}

INTERVIEW Q&A:
Question: {question}
Answer: {answer}

Evaluate the answer on these criteria:
- Technical accuracy and depth
- Relevance to the question asked
- Alignment with position requirements
- Communication clarity
- Specific examples or evidence provided

Return ONLY this JSON format:
{{
  "score": [integer from 0-10 where 10 is perfect],
  "summary": "[1-2 sentence summary of answer quality and key strengths/weaknesses]"
}}

Scoring guide:
- 0-2: Poor/incorrect answer, major issues
- 3-4: Below average, some issues
- 5-6: Average answer, meets basic expectations
- 7-8: Good answer, shows competence
- 9-10: Excellent answer, exceeds expectations"""

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "temperature": 0.0,  # Zero temperature for consistent scoring
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": user_prompt
            }
        ]
    }

    # Retry logic with exponential backoff for throttling
    max_retries = 3
    base_delay = 1.0  # Start with 1 second

    for attempt in range(max_retries + 1):
        try:
            # Add jitter to prevent thundering herd
            if attempt > 0:
                jitter = random.uniform(0.5, 1.5)
                delay = (base_delay * (2 ** (attempt - 1))) * jitter
                print(
                    f"Attempt {attempt + 1}, waiting {delay:.2f} seconds before retry")
                time.sleep(delay)

            response = bedrock_client.invoke_model(
                modelId=inference_profile_arn,
                body=json.dumps(request_body),
                contentType='application/json',
                accept='application/json'
            )

            response_body = json.loads(response['body'].read())
            content_text = response_body['content'][0]['text']
            break  # Success, exit retry loop

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ThrottlingException' and attempt < max_retries:
                print(
                    f"Throttling detected, attempt {attempt + 1}/{max_retries + 1}")
                continue
            else:
                print(f"Bedrock error after {attempt + 1} attempts: {str(e)}")
                raise
        except Exception as e:
            print(f"Unexpected error on attempt {attempt + 1}: {str(e)}")
            if attempt < max_retries:
                continue
            raise

        # Parse the JSON response
        try:
            score_data = json.loads(content_text.strip())

            # Validate response format
            if not isinstance(
                    score_data,
                    dict) or 'score' not in score_data or 'summary' not in score_data:
                raise ValueError("Invalid response format")

            # Validate score range
            score = int(score_data['score'])
            if score < 0 or score > 10:
                raise ValueError(f"Score out of range: {score}")

            return {
                'score': score,
                'summary': score_data['summary'].strip()
            }

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"Failed to parse scoring response: {content_text}")
            print(f"Parse error: {str(e)}")

            # Fallback: try to extract JSON from wrapped text
            content_clean = content_text.strip()
            if content_clean.startswith('```json'):
                content_clean = content_clean[7:-3].strip()
            elif content_clean.startswith('```'):
                content_clean = content_clean[3:-3].strip()

            try:
                score_data = json.loads(content_clean)
                # Default to 5 if missing
                score = int(score_data.get('score', 5))
                score = max(0, min(10, score))  # Clamp to 0-10 range

                return {'score': score, 'summary': score_data.get(
                    'summary', 'Unable to generate summary').strip()}
            except (json.JSONDecodeError, ValueError):
                print(f"Failed to parse after cleanup: {content_clean}")
                # Ultimate fallback
                return {
                    'score': 5,
                    'summary': 'Unable to score answer due to processing error'
                }

    except Exception as e:
        print(
            f"Error calling Bedrock for answer scoring after all retries: {str(e)}")
        return {
            'score': 5,
            'summary': 'Unable to score answer due to system error - please retry later'}


def update_qa_with_score(dynamodb, qa_id, score_result):
    """
    Update the Q&A record with the score and summary.
    """
    try:
        table = dynamodb.Table('interview_qa')

        table.update_item(
            Key={'id': qa_id},
            UpdateExpression='SET answer_score = :score, answer_summary = :summary, processing_status = :status',
            ExpressionAttributeValues={
                ':score': Decimal(str(score_result['score'])),
                ':summary': score_result['summary'],
                ':status': 'scored'
            }
        )

    except Exception as e:
        print(f"Error updating Q&A {qa_id} with score: {str(e)}")
        raise

import json
import boto3
import uuid
from datetime import datetime


def handler(event, context):
    """
    Process interview transcription workflow:
    1. Load vacancy description from S3
    2. Start Transcribe job with speaker identification
    3. Wait for completion and get results
    4. Save to DynamoDB
    """

    s3 = boto3.client('s3')
    transcribe = boto3.client('transcribe')
    dynamodb = boto3.resource('dynamodb')

    # Get input from Step Functions
    bucket = event['bucket']
    key = event['key']
    position_name = event['position_name']
    interview_id = event['interview_id']
    created_at = event['created_at']

    try:
        # Step 1: Load vacancy description
        vacancy_key = f"{position_name}/vacancy.txt"
        try:
            vacancy_response = s3.get_object(Bucket=bucket, Key=vacancy_key)
            position_description = vacancy_response['Body'].read().decode(
                'utf-8')
        except s3.exceptions.NoSuchKey:
            print(f"Vacancy file not found: {vacancy_key}")
            position_description = f"Position: {position_name}"

        # Step 2: Start Transcribe job
        job_name = f"interview-{interview_id}"
        audio_uri = f"s3://{bucket}/{key}"

        transcribe_response = transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={'MediaFileUri': audio_uri},
            MediaFormat=key.split('.')[-1].lower(),
            LanguageCode='ru-RU',
            Settings={
                'ShowSpeakerLabels': True,
                'MaxSpeakerLabels': 2,  # Interviewer and Candidate
                'ChannelIdentification': False
            },
            OutputBucketName=bucket,
            OutputKey=f"transcriptions/{job_name}.json"
        )

        return {
            'statusCode': 200,
            'job_name': job_name,
            'bucket': bucket,
            'key': key,
            'position_name': position_name,
            'position_description': position_description,
            'interview_id': interview_id,
            'created_at': created_at,
            'transcribe_status': 'IN_PROGRESS'
        }

    except Exception as e:
        print(f"Error starting transcription: {str(e)}")
        raise


def check_transcription_status(event, context):
    """
    Check transcription job status and process results when complete.
    """

    transcribe = boto3.client('transcribe')
    s3 = boto3.client('s3')
    dynamodb = boto3.resource('dynamodb')

    job_name = event['job_name']

    try:
        # Check job status
        response = transcribe.get_transcription_job(
            TranscriptionJobName=job_name)
        job_status = response['TranscriptionJob']['TranscriptionJobStatus']

        if job_status == 'COMPLETED':
            # Get transcription results
            transcript_uri = response['TranscriptionJob']['Transcript']['TranscriptFileUri']

            # Parse S3 URI to get bucket and key
            if transcript_uri.startswith('https://'):
                # Handle HTTPS URL format: https://s3.region.amazonaws.com/bucket/key
                # or https://bucket.s3.region.amazonaws.com/key
                if '.s3.' in transcript_uri:
                    # Format: https://bucket.s3.region.amazonaws.com/key
                    uri_without_protocol = transcript_uri.replace('https://', '')
                    parts = uri_without_protocol.split('/')
                    result_bucket = parts[0].split('.')[0]  # Extract bucket from hostname
                    result_key = '/'.join(parts[1:])  # Everything after bucket
                else:
                    # Format: https://s3.region.amazonaws.com/bucket/key
                    uri_without_protocol = transcript_uri.replace('https://', '')
                    parts = uri_without_protocol.split('/')
                    result_bucket = parts[1]  # Second part is bucket
                    result_key = '/'.join(parts[2:])  # Everything after bucket
            else:
                # Handle S3 URI format: s3://bucket/key
                uri_parts = transcript_uri.replace('s3://', '').split('/', 1)
                result_bucket = uri_parts[0]
                result_key = uri_parts[1]

            # Download transcription result
            transcript_response = s3.get_object(
                Bucket=result_bucket, Key=result_key)
            transcript_data = json.loads(
                transcript_response['Body'].read().decode('utf-8'))

            # Extract speaker-separated transcript
            segments = transcript_data['results']['speaker_labels']['segments']
            items = transcript_data['results']['items']

            # Build speaker-separated transcript
            transcript_text = format_speaker_transcript(segments, items)

            # Save to DynamoDB
            table = dynamodb.Table('interview_transcriptions')
            table.put_item(
                Item={
                    'id': event['interview_id'],
                    'position_name': event['position_name'],
                    'position_description': event['position_description'],
                    'interview_transcript': transcript_text,
                    'created_at': event['created_at']
                }
            )

            return {
                'statusCode': 200,
                'transcribe_status': 'COMPLETED',
                'interview_id': event['interview_id'],
                'transcript_length': len(transcript_text)
            }

        elif job_status == 'FAILED':
            raise Exception(
                f"Transcription job failed: {response['TranscriptionJob']['FailureReason']}")

        else:
            return {
                'statusCode': 202,
                'transcribe_status': job_status,
                'job_name': job_name
            }

    except Exception as e:
        print(f"Error checking transcription status: {str(e)}")
        raise


def format_speaker_transcript(segments, items):
    """
    Format transcription with speaker labels (Interviewer/Candidate).
    """

    # Create item lookup by start time
    item_lookup = {}
    for item in items:
        if item['type'] == 'pronunciation':
            start_time = float(item['start_time'])
            item_lookup[start_time] = item['alternatives'][0]['content']

    transcript_lines = []
    current_speaker = None
    current_text = []

    for segment in segments:
        speaker_label = segment['speaker_label']

        # Map speaker labels to meaningful names
        if speaker_label == 'spk_0':
            speaker_name = "Interviewer"
        else:
            speaker_name = "Candidate"

        # If speaker changed, save previous line and start new one
        if current_speaker != speaker_name:
            if current_text:
                transcript_lines.append(
                    f"{current_speaker}: {' '.join(current_text)}")
            current_speaker = speaker_name
            current_text = []

        # Add words from this segment
        for item in segment['items']:
            start_time = float(item['start_time'])
            if start_time in item_lookup:
                current_text.append(item_lookup[start_time])

    # Add final line
    if current_text:
        transcript_lines.append(f"{current_speaker}: {' '.join(current_text)}")

    return '\n\n'.join(transcript_lines)

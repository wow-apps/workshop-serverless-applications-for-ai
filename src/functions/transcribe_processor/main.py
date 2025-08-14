import json
import boto3
import uuid
from datetime import datetime
from decimal import Decimal


def create_technical_vocabulary():
    """
    Create a custom vocabulary for technical interview terms in Russian.
    Returns vocabulary phrases for common programming and IT terms.
    """

    # Common technical terms in Russian interviews
    vocabulary_phrases = [
        # Programming concepts
        "программирование",
        "алгоритм",
        "структура данных",
        "база данных",
        "фреймворк",
        "архитектура",
        "микросервисы",
        "API",
        "REST",
        "GraphQL",
        "Docker",
        "Kubernetes",
        "Git",
        "GitHub",
        "разработка",
        "тестирование",
        "деплой",
        "DevOps",
        "облачные технологии",
        "AWS",
        "Lambda",
        "DynamoDB",

        # Programming languages (as pronounced in Russian)
        "Пайтон",
        "Джава",
        "Джаваскрипт",
        "Тайпскрипт",
        "Реакт",
        "Ноде",
        "С плюс плюс",
        "Си шарп",
        "Го",
        "Раст",

        # Common interview phrases
        "опыт работы",
        "проект",
        "команда",
        "задача",
        "решение",
        "проблема",
        "оптимизация",
        "производительность",
        "масштабируемость",
        "безопасность",
        "код ревью",
        "pull request",
        "merge",
        "branch",
        "commit",

        # Soft skills
        "коммуникация",
        "лидерство",
        "teamwork",
        "agile",
        "scrum",
        "планирование",
        "deadline",
        "milestone"
    ]

    return vocabulary_phrases


def ensure_custom_vocabulary(transcribe_client, vocabulary_name="technical-interview-ru"):
    """
    Ensure custom vocabulary exists for technical interview terms.
    Creates it if it doesn't exist, returns vocabulary status.
    """

    try:
        # Check if vocabulary already exists
        response = transcribe_client.get_vocabulary(VocabularyName=vocabulary_name)
        return response['VocabularyState'], vocabulary_name

    except transcribe_client.exceptions.NotFoundException:
        # Vocabulary doesn't exist, create it
        vocabulary_phrases = create_technical_vocabulary()

        try:
            transcribe_client.create_vocabulary(
                VocabularyName=vocabulary_name,
                LanguageCode='ru-RU',
                Phrases=vocabulary_phrases
            )
            return 'PENDING', vocabulary_name

        except Exception as e:
            print(f"Failed to create custom vocabulary: {str(e)}")
            return None, None

    except Exception as e:
        print(f"Error checking vocabulary: {str(e)}")
        return None, None


def handler(event, context):
    """
    Process interview transcription workflow with enhanced Russian language support:
    1. Load vacancy description from S3
    2. Setup custom vocabulary for technical interview terms
    3. Start Transcribe job with optimized settings for Russian language:
       - Speaker identification for interviewer/candidate
       - Multiple alternatives with confidence scores
       - Custom vocabulary for technical terms
       - Enhanced punctuation and formatting
    4. Wait for completion and get results
    5. Save to DynamoDB with confidence-based text selection
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

        # Step 2: Setup custom vocabulary for technical terms
        vocabulary_state, vocabulary_name = ensure_custom_vocabulary(transcribe)

        # Step 3: Start Transcribe job
        job_name = f"interview-{interview_id}"
        audio_uri = f"s3://{bucket}/{key}"

        # Enhanced transcription settings for better Russian language accuracy
        transcribe_settings = {
            'ShowSpeakerLabels': True,
            'MaxSpeakerLabels': 2,
            'ChannelIdentification': False,
            'ShowAlternatives': True,
            'MaxAlternatives': 3,
            'VocabularyFilterMethod': 'remove',
        }

        # Add custom vocabulary if it's ready
        if vocabulary_state == 'READY' and vocabulary_name:
            transcribe_settings['VocabularyName'] = vocabulary_name
            print(f"Using custom vocabulary: {vocabulary_name}")
        elif vocabulary_state == 'PENDING':
            print(f"Custom vocabulary {vocabulary_name} is being created, using default settings")
        else:
            print("Using default vocabulary settings")

        # Prepare transcription job parameters (simplified to avoid execution role issues)
        job_params = {
            'TranscriptionJobName': job_name,
            'Media': {'MediaFileUri': audio_uri},
            'MediaFormat': key.split('.')[-1].lower(),
            'LanguageCode': 'ru-RU',
            'Settings': transcribe_settings,
            'OutputBucketName': bucket,
            'OutputKey': f"transcriptions/{job_name}.json"
        }

        transcribe_response = transcribe.start_transcription_job(**job_params)

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

            # Extract raw transcript data for chunking
            segments = transcript_data['results']['speaker_labels']['segments']
            items = transcript_data['results']['items']

            # Build speaker-separated transcript (for backwards compatibility)
            transcript_text = format_speaker_transcript(segments, items)

            # Build utterances with timestamps for chunking
            utterances = build_utterances_with_timestamps(segments, items)

            # Save to DynamoDB without large raw data (due to 400KB item size limit)
            # For large transcripts, we'll store utterances for chunking and skip raw data
            table = dynamodb.Table('interview_transcriptions')

            # Calculate sizes to determine what we can store
            transcript_size = len(transcript_text.encode('utf-8'))
            utterances_size = len(str(utterances).encode('utf-8'))

            # DynamoDB item size limit is 400KB, leave room for metadata
            MAX_SAFE_SIZE = 350 * 1024  # 350KB to be safe

            # Prepare the item
            item = {
                'id': event['interview_id'],
                'position_name': event['position_name'],
                'position_description': event['position_description'],
                'created_at': event['created_at'],
                'processing_status': 'transcribed',
                'transcript_size_bytes': transcript_size,
                'utterance_count': len(utterances),
                'total_duration_ms': utterances[-1]['end_time_ms'] if utterances else 0
            }

            # Only store transcript text if it fits
            if transcript_size < MAX_SAFE_SIZE // 2:  # Use half the space for transcript
                item['interview_transcript'] = transcript_text
            else:
                # For very large transcripts, store summary info only
                item[
                    'interview_transcript'] = f"[Large transcript - {len(utterances)} utterances, {transcript_size} bytes]"
                print(f"Transcript too large ({transcript_size} bytes), storing summary only")

            # Store utterances separately due to size
            # We'll chunk and process them in the next step
            # For now, just store a sample for debugging
            if len(utterances) > 10:
                item['utterances_sample'] = utterances[:5] + utterances[-5:]  # First and last 5
            else:
                item['utterances_sample'] = utterances

            table.put_item(Item=item)

            # Store full utterances in a separate location (S3) for chunking
            s3_key = f"utterances/{event['interview_id']}_utterances.json"
            s3.put_object(
                Bucket=event['bucket'],
                Key=s3_key,
                Body=json.dumps(utterances, default=str),
                ContentType='application/json'
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
    Enhanced to use confidence scores and best alternatives for Russian language.
    """

    # Create item lookup by start time with confidence-based selection
    item_lookup = {}
    for item in items:
        if item['type'] == 'pronunciation':
            start_time = float(item['start_time'])

            # Select best alternative based on confidence score
            best_alternative = item['alternatives'][0]  # Default to first
            best_confidence = float(best_alternative.get('confidence', '0'))

            # Check all alternatives for highest confidence
            for alt in item['alternatives']:
                confidence = float(alt.get('confidence', '0'))
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_alternative = alt

            # Only use alternatives with confidence > 0.7 for Russian
            if best_confidence > 0.7:
                item_lookup[start_time] = best_alternative['content']
            else:
                # Fallback to first alternative but mark as uncertain
                item_lookup[start_time] = f"[{best_alternative['content']}]"

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


def build_utterances_with_timestamps(segments, items):
    """
    Build structured utterances with timestamps for efficient chunking.
    Each utterance represents a continuous speech from one speaker.
    """

    # Create item lookup by start time with confidence-based selection
    item_lookup = {}
    for item in items:
        if item['type'] == 'pronunciation':
            start_time = float(item['start_time'])
            end_time = float(item['end_time'])

            # Select best alternative based on confidence score
            best_alternative = item['alternatives'][0]
            best_confidence = float(best_alternative.get('confidence', '0'))

            for alt in item['alternatives']:
                confidence = float(alt.get('confidence', '0'))
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_alternative = alt

            item_lookup[start_time] = {
                'word': best_alternative['content'],
                'start_time': Decimal(str(start_time)),
                'end_time': Decimal(str(end_time)),
                'confidence': Decimal(str(best_confidence))
            }

    utterances = []
    current_speaker = None
    current_words = []
    current_start_time = None
    current_end_time = None
    utterance_id = 0

    for segment in segments:
        speaker_label = segment['speaker_label']

        # Map speaker labels to meaningful names
        speaker_name = "Interviewer" if speaker_label == 'spk_0' else "Candidate"

        # If speaker changed, save previous utterance and start new one
        if current_speaker != speaker_name:
            if current_words and current_speaker:
                # Calculate average confidence as Decimal
                avg_confidence = Decimal('0')
                if current_words:
                    confidence_sum = sum(w['confidence'] for w in current_words)
                    avg_confidence = confidence_sum / Decimal(str(len(current_words)))

                utterances.append({
                    'utterance_id': utterance_id,
                    'speaker': current_speaker,
                    'text': ' '.join([w['word'] for w in current_words]),
                    'start_time_ms': int(float(current_start_time) * 1000),
                    'end_time_ms': int(float(current_end_time) * 1000),
                    'word_count': len(current_words),
                    'avg_confidence': avg_confidence
                })
                utterance_id += 1

            current_speaker = speaker_name
            current_words = []
            current_start_time = None
            current_end_time = None

        # Add words from this segment
        for item in segment['items']:
            start_time = float(item['start_time'])
            if start_time in item_lookup:
                word_data = item_lookup[start_time]
                current_words.append(word_data)

                # Update utterance timing
                if current_start_time is None:
                    current_start_time = word_data['start_time']
                current_end_time = word_data['end_time']

    # Add final utterance
    if current_words and current_speaker:
        # Calculate average confidence as Decimal
        avg_confidence = Decimal('0')
        if current_words:
            confidence_sum = sum(w['confidence'] for w in current_words)
            avg_confidence = confidence_sum / Decimal(str(len(current_words)))

        utterances.append({
            'utterance_id': utterance_id,
            'speaker': current_speaker,
            'text': ' '.join([w['word'] for w in current_words]),
            'start_time_ms': int(float(current_start_time) * 1000),
            'end_time_ms': int(float(current_end_time) * 1000),
            'word_count': len(current_words),
            'avg_confidence': avg_confidence
        })

    return utterances

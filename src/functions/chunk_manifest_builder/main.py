import json
import boto3
from decimal import Decimal


def handler(event, context):
    """
    Build chunk manifest for processing large interview transcripts.
    Groups utterances into 3-7 minute chunks with small overlap to avoid splitting Q&A boundaries.
    """
    
    dynamodb = boto3.resource('dynamodb')
    
    interview_id = event['interview_id']
    position_name = event['position_name']
    
    try:
        # Get transcription metadata from DynamoDB
        table = dynamodb.Table('interview_transcriptions')
        response = table.get_item(Key={'id': interview_id})
        
        if 'Item' not in response:
            raise Exception(f"Interview transcription not found: {interview_id}")
        
        interview_data = response['Item']
        position_description = interview_data['position_description']
        
        # Get full utterances from S3 (stored there due to DynamoDB size limits)
        s3 = boto3.client('s3')
        utterances_key = f"utterances/{interview_id}_utterances.json"
        
        # Try to get bucket name from various sources
        bucket_name = None
        
        # First, try to get from interview data if stored
        if 'bucket_name' in interview_data:
            bucket_name = interview_data['bucket_name']
        
        # If not found, try to get from event (if passed from previous step)
        elif 'bucket' in event:
            bucket_name = event['bucket']
        
        # Last resort: use default pattern
        else:
            bucket_name = "interview-artifacts"
            print(f"Using default bucket name: {bucket_name}")
        
        try:
            utterances_response = s3.get_object(Bucket=bucket_name, Key=utterances_key)
            utterances = json.loads(utterances_response['Body'].read().decode('utf-8'))
        except s3.exceptions.NoSuchKey:
            raise Exception(f"Utterances file not found: s3://{bucket_name}/{utterances_key}")
        except Exception as e:
            raise Exception(f"Error reading utterances from S3: {str(e)}")
        
        # Build chunk manifest
        chunks = build_chunks(utterances, position_name, interview_id)
        
        # Save chunks to DynamoDB for Map processing
        chunk_table = dynamodb.Table('interview_chunks')
        
        for chunk in chunks:
            # Convert float values to Decimal for DynamoDB
            chunk_item = convert_to_dynamodb_format(chunk)
            chunk_table.put_item(Item=chunk_item)
        
        # Update processing status
        table.update_item(
            Key={'id': interview_id},
            UpdateExpression='SET processing_status = :status, chunk_count = :count',
            ExpressionAttributeValues={
                ':status': 'chunked',
                ':count': len(chunks)
            }
        )
        
        return {
            'statusCode': 200,
            'interview_id': interview_id,
            'position_name': position_name,
            'position_description': position_description,
            'bucket_name': bucket_name,  # Include bucket name for chunk processing
            'chunk_count': len(chunks),
            'total_duration_ms': chunks[-1]['end_ms'] if chunks else 0,
            'chunks': [{'chunk_index': c['chunk_index'], 'start_ms': c['start_ms'], 'end_ms': c['end_ms']} for c in chunks]
        }
        
    except Exception as e:
        print(f"Error building chunk manifest: {str(e)}")
        raise


def build_chunks(utterances, position_name, interview_id):
    """
    Build optimized chunks for Q&A extraction.
    Target: 3-7 minutes per chunk with 15-second overlap.
    """
    
    if not utterances:
        return []
    
    chunks = []
    chunk_index = 0
    
    # Configuration
    TARGET_CHUNK_DURATION_MS = 4 * 60 * 1000  # 4 minutes target
    MIN_CHUNK_DURATION_MS = 3 * 60 * 1000     # 3 minutes minimum
    MAX_CHUNK_DURATION_MS = 7 * 60 * 1000     # 7 minutes maximum
    OVERLAP_MS = 15 * 1000                     # 15 seconds overlap
    
    current_start_idx = 0
    
    while current_start_idx < len(utterances):
        chunk_start_time = utterances[current_start_idx]['start_time_ms']
        chunk_utterances = []
        current_idx = current_start_idx
        
        # Build chunk until we reach target duration or end of utterances
        while current_idx < len(utterances):
            utterance = utterances[current_idx]
            chunk_duration = utterance['end_time_ms'] - chunk_start_time
            
            # Add utterance to chunk
            chunk_utterances.append(utterance)
            
            # Check if we should end this chunk
            if chunk_duration >= TARGET_CHUNK_DURATION_MS:
                # Try to find a natural break point (end of candidate answer)
                break_point = find_natural_break_point(utterances, current_idx, chunk_start_time, MAX_CHUNK_DURATION_MS)
                if break_point != -1:
                    # Adjust chunk to natural break
                    chunk_utterances = utterances[current_start_idx:break_point + 1]
                break
            elif chunk_duration >= MAX_CHUNK_DURATION_MS:
                # Hard limit reached
                break
            
            current_idx += 1
        
        # Ensure minimum chunk size unless it's the last chunk
        if len(chunk_utterances) > 0:
            chunk_duration = chunk_utterances[-1]['end_time_ms'] - chunk_start_time
            if chunk_duration < MIN_CHUNK_DURATION_MS and current_idx < len(utterances) - 1:
                # Extend chunk to minimum duration
                while current_idx < len(utterances):
                    utterance = utterances[current_idx]
                    chunk_utterances.append(utterance)
                    chunk_duration = utterance['end_time_ms'] - chunk_start_time
                    if chunk_duration >= MIN_CHUNK_DURATION_MS:
                        break
                    current_idx += 1
        
        if chunk_utterances:
            # Create chunk manifest item
            chunk_text = build_chunk_text(chunk_utterances)
            speakers = list(set(u['speaker'] for u in chunk_utterances))
            
            chunk = {
                'position': position_name,
                'interview_id': interview_id,
                'chunk_index': chunk_index,
                'start_ms': chunk_utterances[0]['start_time_ms'],
                'end_ms': chunk_utterances[-1]['end_time_ms'],
                'utterance_ids': [u['utterance_id'] for u in chunk_utterances],
                'text': chunk_text,
                'speakers': speakers,
                'utterance_count': len(chunk_utterances),
                'word_count': sum(u['word_count'] for u in chunk_utterances),
                'avg_confidence': sum(u['avg_confidence'] for u in chunk_utterances) / len(chunk_utterances),
                'duration_ms': chunk_utterances[-1]['end_time_ms'] - chunk_utterances[0]['start_time_ms']
            }
            
            chunks.append(chunk)
            chunk_index += 1
        
        # Calculate next start position with overlap
        if current_idx >= len(utterances):
            break
            
        # Find overlap start position
        overlap_start_time = chunk_utterances[-1]['end_time_ms'] - OVERLAP_MS
        next_start_idx = current_idx
        
        # Find utterance that starts the overlap
        for i in range(len(chunk_utterances) - 1, -1, -1):
            if chunk_utterances[i]['start_time_ms'] >= overlap_start_time:
                next_start_idx = current_start_idx + i
                break
        
        current_start_idx = max(next_start_idx, current_start_idx + 1)
    
    return chunks


def find_natural_break_point(utterances, current_idx, chunk_start_time, max_duration_ms):
    """
    Find a natural break point (end of candidate answer) within the maximum duration.
    """
    
    # Look ahead for natural break (candidate finishing an answer)
    for i in range(current_idx, min(len(utterances), current_idx + 20)):  # Look at next 20 utterances
        utterance = utterances[i]
        
        # Check if we're past max duration
        if utterance['end_time_ms'] - chunk_start_time > max_duration_ms:
            break
        
        # Natural break: candidate finishes speaking and interviewer starts
        if (utterance['speaker'] == 'Candidate' and 
            i + 1 < len(utterances) and 
            utterances[i + 1]['speaker'] == 'Interviewer'):
            return i
    
    return -1  # No natural break found


def build_chunk_text(chunk_utterances):
    """
    Build formatted text for the chunk with speaker labels and timestamps.
    """
    
    lines = []
    for utterance in chunk_utterances:
        timestamp = format_timestamp(utterance['start_time_ms'])
        lines.append(f"[{timestamp}] {utterance['speaker']}: {utterance['text']}")
    
    return '\n'.join(lines)


def format_timestamp(ms):
    """
    Format milliseconds to MM:SS timestamp.
    """
    
    seconds = ms // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def convert_to_dynamodb_format(chunk):
    """
    Convert chunk data to DynamoDB-compatible format (Decimal instead of float).
    """
    
    return {
        'id': f"{chunk['interview_id']}#{chunk['chunk_index']}",  # Composite key
        'position': chunk['position'],
        'interview_id': chunk['interview_id'],
        'chunk_index': chunk['chunk_index'],
        'start_ms': Decimal(str(chunk['start_ms'])),
        'end_ms': Decimal(str(chunk['end_ms'])),
        'utterance_ids': chunk['utterance_ids'],
        'text': chunk['text'],
        'speakers': chunk['speakers'],
        'utterance_count': chunk['utterance_count'],
        'word_count': chunk['word_count'],
        'avg_confidence': Decimal(str(chunk['avg_confidence'])),
        'duration_ms': Decimal(str(chunk['duration_ms'])),
        'processing_status': 'pending'
    }
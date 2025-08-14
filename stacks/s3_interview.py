from aws_cdk import (
    aws_s3,
    aws_s3_deployment,
    aws_s3_notifications as s3n,
    Stack, RemovalPolicy,
)
from constructs import Construct


class InterviewBucketStack(Stack):
    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        bucket = aws_s3.Bucket(
            self,
            "InterviewBucket",
            bucket_name="interview-artifacts",
            public_read_access=False,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
        )

        self.upload_bucket = bucket

        # Deploy static files from src/static/interview to the bucket
        aws_s3_deployment.BucketDeployment(
            self,
            "InterviewStaticDeployment",
            sources=[aws_s3_deployment.Source.asset("src/static/interview")],
            destination_bucket=bucket,
        )

    def add_event_notifications(self, lambda_function):
        """Add S3 event notifications for audio files to trigger Lambda function."""

        # Add S3 event notifications for different audio file types
        audio_extensions = [".mp3", ".m4a", ".wav", ".flac"]

        for ext in audio_extensions:
            self.upload_bucket.add_event_notification(
                aws_s3.EventType.OBJECT_CREATED,
                s3n.LambdaDestination(lambda_function),
                aws_s3.NotificationKeyFilter(suffix=ext)
            )

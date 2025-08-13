from aws_cdk import (
    aws_s3,
    aws_s3_deployment,
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
            bucket_name="itcraft-ai-interview-bucket",
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

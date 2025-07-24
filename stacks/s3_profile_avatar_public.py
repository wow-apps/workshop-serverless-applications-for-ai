from aws_cdk import (
    Stack,
    aws_s3 as s3,
    RemovalPolicy,
)
from constructs import Construct

class ProfileAvatarPublicBucketStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a public S3 bucket for profile avatars
        self.bucket = s3.Bucket(
            self,
            "ProfileAvatarPublicBucket",
            bucket_name="workshop-profile-avatar-public",
            block_public_access=s3.BlockPublicAccess.BLOCK_ACLS,
            public_read_access=True,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
            website_index_document="index.html",
            website_error_document="error.html",
        )

from aws_cdk import (
    aws_kms as kms,
    aws_iam as iam,
    Stack,
)
from constructs import Construct


class KmsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create the KMS key
        self.kms_key = kms.Key(
            self,
            "GlobalKmsKey",
            enable_key_rotation=True,
        )

        # Add policy to allow Lambda to use the key
        self.kms_key.add_to_resource_policy(
            iam.PolicyStatement(
                actions=[
                    "kms:Encrypt",
                    "kms:Decrypt",
                    "kms:GenerateDataKey",
                ],
                resources=["*"],
                principals=[iam.ServicePrincipal("lambda.amazonaws.com")],
                conditions={
                    "StringEquals": {
                        "kms:CallerAccount": self.account,
                        "kms:ViaService": f"lambda.{self.region}.amazonaws.com",
                    }
                },
            )
        )

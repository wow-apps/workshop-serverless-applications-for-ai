from aws_cdk import (
    aws_dynamodb as dynamodb,
    Stack,
    RemovalPolicy,
)
from constructs import Construct


class DynamoDbStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        kms_key,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Interview Transcriptions Table
        # PK: id (uuid)
        # Attributes: id, position_name, position_description, interview_transcript, created_at
        self.interview_transcriptions_table = dynamodb.Table(
            self,
            "InterviewTranscriptionsTable",
            table_name="interview_transcriptions",
            partition_key=dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=kms_key,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
        )

        # Add GSI for querying by position_name
        self.interview_transcriptions_table.add_global_secondary_index(
            index_name="GSI1",
            partition_key=dynamodb.Attribute(
                name="position_name",
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL
        )

        # Interview Q&A Table
        # PK: id (uuid)
        # Attributes: id, interview_id, question, answer
        self.interview_qa_table = dynamodb.Table(
            self,
            "InterviewQATable", 
            table_name="interview_qa",
            partition_key=dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=kms_key,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
        )

        # Add GSI for querying by interview_id
        self.interview_qa_table.add_global_secondary_index(
            index_name="GSI1",
            partition_key=dynamodb.Attribute(
                name="interview_id",
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL
        )

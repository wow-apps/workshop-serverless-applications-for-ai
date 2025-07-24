import os

env_account: str = os.getenv("CDK_ACCOUNT")
env_region: str = os.getenv("CDK_REGION")
cloud_environment: str = os.getenv("CLOUD_ENVIRONMENT", "workshop-dev")

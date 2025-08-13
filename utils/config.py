import os
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

env_account: str = os.getenv("CDK_ACCOUNT")
env_region: str = os.getenv("CDK_REGION")
cloud_environment: str = os.getenv("CLOUD_ENVIRONMENT", "workshop-dev")

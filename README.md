# workshop-serverless-applications-for-ai

```shell
source venv/bin/activate
poetry install --no-root

cdk bootstrap --profile interview.workshop.itcraft
cdk diff --all --profile interview.workshop.itcraft
cdk deploy --all --require-approval never --profile 
```
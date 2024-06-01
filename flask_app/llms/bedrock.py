import boto3
import json

class BedrockLLM:
    def __init__(self, bedrock_runtime, model_name):
        self.bedrock_runtime = bedrock_runtime
        self.model_name = model_name

    def invoke_model(self, prompt, max_gen_len=512, temperature=0.5, top_p=0.9):
        kwargs = {
            "modelId": self.model_name,
            "contentType": "application/json",
            "accept": "application/json",
            "body": json.dumps({
                "prompt": prompt,
                "max_gen_len": max_gen_len,
                "temperature": temperature,
                "top_p": top_p
            })
        }
        response = self.bedrock_runtime.invoke_model(**kwargs)
        bedrock_response = json.loads(response['body'].read())
        return bedrock_response['generation']

    def run(self, text, stop):
        return self.invoke_model(prompt=text)

def load_bedrock_prompt(model_name):
    # Customize this function based on how you manage prompts
    # For simplicity, returning a basic prompt
    return f"Answer the following question using the context provided: {{context}} \n\n Question: {{question}} \n Answer:"
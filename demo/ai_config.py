# AI Configuration File
# Replace with your actual API tokens

import os

def setup_api_keys():
    """Configure API keys for Jupyter AI"""
    
    # OpenAI Configuration
    os.environ['OPENAI_API_KEY'] = ''
    os.environ['OPENAI_API_BASE'] = 'https://api.portkey.ai/v1'
    
    # Anthropic Configuration  
    # os.environ['ANTHROPIC_API_KEY'] = 'your-anthropic-api-key-here'
    
    # Other providers (uncomment as needed)
    # os.environ['COHERE_API_KEY'] = 'your-cohere-api-key-here'
    # os.environ['HUGGINGFACE_API_KEY'] = 'your-huggingface-api-key-here'
    
    print("🔑 API keys configured (update ai_config.py with actual keys)")

if __name__ == "__main__":
    setup_api_keys()

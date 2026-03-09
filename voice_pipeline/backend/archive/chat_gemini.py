import asyncio
from google import genai
from config import GEMINI_API_KEY, LLM_MODEL

async def chat():
    print(f"--- Gemini Text Chat ({LLM_MODEL}) ---")
    print("Type 'exit' or 'quit' to stop.\n")
    
    client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1alpha'})
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit"]:
            break
            
        try:
            # Use streaming for a better experience
            print("Gemini: ", end="", flush=True)
            response_stream = await client.aio.models.generate_content_stream(
                model=LLM_MODEL,
                contents=user_input,
            )
            
            async for chunk in response_stream:
                if chunk.text:
                    print(chunk.text, end="", flush=True)
            print("\n")
            
        except Exception as e:
            print(f"\nError: {e}\n")

if __name__ == "__main__":
    try:
        asyncio.run(chat())
    except KeyboardInterrupt:
        print("\nGoodbye!")

import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools import get_weather_forecast, get_mandi_prices

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(timeout=30000),  # 30 seconds per AI call
)

# Models from your own list. Older ones first because they are usually less busy.
MODELS = [
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
]

SYSTEM_PROMPT = """You are a friendly agricultural advisor for Indian farmers.
Use the tools to fetch REAL, LIVE weather forecasts and mandi prices before advising.
Rules:
- Call get_weather_forecast for the farmer's location when weather matters.
  Always pass the farmer's state too.
- Call get_mandi_prices when the farmer asks about selling or prices.
- Give short, simple, practical advice (irrigate or not, sell now or wait, etc.).
- Mention the actual numbers you found (rain chance, price per quintal).
- If mandi prices are unavailable, say clearly that live prices could not be
  fetched right now. Never guess or invent prices.
- If a price note says the prices are from other states, tell the farmer they
  are not local prices.
- Reply in the same language the farmer used.
"""

TOOLS = {
    "get_weather_forecast": get_weather_forecast,
    "get_mandi_prices": get_mandi_prices,
}

TOOL_DECLARATIONS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="get_weather_forecast",
        description="Get a live daily weather forecast (temperature, rain, wind) for a place in India.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "place": types.Schema(type="STRING", description="Village or city name, e.g. Rourkela"),
                "state": types.Schema(type="STRING", description="Indian state, e.g. Odisha. Optional but recommended."),
                "days": types.Schema(type="INTEGER", description="Number of forecast days, 1 to 5"),
            },
            required=["place"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_mandi_prices",
        description="Get live mandi (market) prices in INR per quintal for a crop from data.gov.in.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "commodity": types.Schema(type="STRING", description="Crop name, e.g. Potato, Wheat, Paddy"),
                "state": types.Schema(type="STRING", description="Indian state, e.g. Odisha. Optional."),
                "limit": types.Schema(type="INTEGER", description="Max number of markets to return, up to 5"),
            },
            required=["commodity"],
        ),
    ),
])


def _log(on_step, text):
    print(text, flush=True)
    if on_step:
        on_step(text)


def _call_model(model, contents, config):
    """Call one model once. Prints the real error if it fails."""
    try:
        response = client.models.generate_content(
            model=model, contents=contents, config=config
        )
        return response, None
    except Exception as e:
        print(f"  [{model}] failed: {str(e)[:200]}", flush=True)
        return None, e


def _generate(contents, config, on_step):
    """Try each model in order until one answers."""
    error = None
    for model in MODELS:
        _log(on_step, f"Thinking with {model}...")
        response, error = _call_model(model, contents, config)
        if response is not None:
            return response, None
        time.sleep(1)
    return None, error


def run_agent(question: str, on_step=None):
    """Run the agent loop. on_step(text) is called for each step."""
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[TOOL_DECLARATIONS],
    )
    contents = [types.Content(role="user", parts=[types.Part(text=question)])]

    for _round in range(5):  # at most 5 tool rounds
        response, error = _generate(contents, config, on_step)
        if response is None:
            return (
                "Sorry, the AI service is not available right now. "
                f"Please try again in a few minutes. ({str(error)[:200]})"
            )

        candidate = response.candidates[0]
        parts = candidate.content.parts or []
        calls = [p.function_call for p in parts if p.function_call]

        if not calls:
            return response.text or "Sorry, I could not produce an answer."

        contents.append(candidate.content)
        result_parts = []
        for call in calls:
            args = dict(call.args)
            _log(on_step, f"Using tool: {call.name}({args})")
            func = TOOLS.get(call.name)
            try:
                result = func(**args) if func else {"error": f"Unknown tool {call.name}"}
            except Exception as e:
                result = {"error": str(e)}
            result_parts.append(
                types.Part.from_function_response(name=call.name, response={"result": result})
            )
        contents.append(types.Content(role="user", parts=result_parts))

    return "Sorry, I could not finish in time. Please try a simpler question."


if __name__ == "__main__":
    answer = run_agent(
        "Farmer details: location = Rourkela, state = Odisha, crop = Potato.\n"
        "Question: Should I irrigate this week, and should I sell now?"
    )
    print()
    print(answer)
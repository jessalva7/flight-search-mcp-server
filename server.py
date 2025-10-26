#!/usr/bin/env python3
"""Flight Search MCP Server using SearchAPI.io Google Flights API"""

import os
from typing import Optional
from mcp.server.fastmcp import FastMCP
import httpx

mcp = FastMCP("flight-search")

SEARCHAPI_KEY = os.getenv("SEARCHAPI_KEY", )
SEARCHAPI_URL = "https://www.searchapi.io/api/v1/search"


def format_flight_results(data: dict) -> dict:
    """Format the API response into a cleaner structure."""
    try:
        result = {
            "search_info": {
                "departure": data.get("search_parameters", {}).get("departure_id"),
                "arrival": data.get("search_parameters", {}).get("arrival_id"),
                "outbound_date": data.get("search_parameters", {}).get("outbound_date"),
                "return_date": data.get("search_parameters", {}).get("return_date"),
                "flight_type": data.get("search_parameters", {}).get("flight_type"),
            },
            "best_flights": [],
            "other_flights": [],
        }

        # Format best flights (limit to 3)
        for flight in data.get("best_flights", [])[:3]:
            flight_legs = []
            for leg in flight.get("flights", []):
                flight_legs.append({
                    "airport": f"{leg['departure_airport'].get('id')} -> {leg['arrival_airport'].get('id')}",
                    "time": f"{leg['departure_airport'].get('time')} -> {leg['arrival_airport'].get('time')}",
                    "date": f"{leg['departure_airport'].get('date')} -> {leg['arrival_airport'].get('date')}",
                })
            
            result["best_flights"].append({
                "price": flight.get("price"),
                "airline": flight["flights"][0].get("airline") if flight.get("flights") else None,
                "flight_number": flight["flights"][0].get("flight_number") if flight.get("flights") else None,
                "flights": flight_legs,
                "duration_minutes": flight.get("total_duration"),
                "is_overnight": flight["flights"][0].get("is_overnight", False) if flight.get("flights") else False,
                "carbon_emissions_kg": flight.get("carbon_emissions", {}).get("this_flight", 0) / 1000,
            })

        # Format other flights (limit to 3 for brevity)
        for flight in data.get("other_flights", [])[:3]:
            result["other_flights"].append({
                "price": flight.get("price"),
                "airline": flight["flights"][0].get("airline") if flight.get("flights") else None,
                "flight_number": flight["flights"][0].get("flight_number") if flight.get("flights") else None,
                "departure_time": flight["flights"][0]["departure_airport"].get("time") if flight.get("flights") else None,
                "arrival_time": flight["flights"][0]["arrival_airport"].get("time") if flight.get("flights") else None,
                "duration_minutes": flight.get("total_duration"),
            })

        return result
    except (KeyError, IndexError, TypeError) as e:
        # If formatting fails, return raw data
        return {"error": f"Failed to format response: {str(e)}", "raw_data": data}


@mcp.tool()
async def search_flights(
    departure_id: str,
    arrival_id: str,
    outbound_date: str,
    return_date: Optional[str] = None,
    flight_type: str = "round_trip",
) -> dict:
    """Search for flights between airports with specified dates.

    Args:
        departure_id: Departure airport code (e.g., JFK, LAX)
        arrival_id: Arrival airport code (e.g., MAD, LHR)
        outbound_date: Outbound date in YYYY-MM-DD format
        return_date: Return date in YYYY-MM-DD format (optional for one-way)
        flight_type: Type of flight - "round_trip" or "one_way" (default: round_trip)

    Returns:
        Formatted flight search results with best flights, other options, and price insights
    """
    try:
        params = {
            "engine": "google_flights",
            "flight_type": flight_type,
            "departure_id": departure_id.upper(),
            "arrival_id": arrival_id.upper(),
            "outbound_date": outbound_date,
            "api_key": SEARCHAPI_KEY,
        }

        if return_date:
            params["return_date"] = return_date

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(SEARCHAPI_URL, params=params)
            response.raise_for_status()
            data = response.json()

            # Check for API errors
            if "error" in data:
                return {
                    "error": data["error"],
                    "message": "API returned an error",
                }

            # Format and return results
            return format_flight_results(data)

    except httpx.HTTPStatusError as e:
        return {
            "error": f"HTTP {e.response.status_code}",
            "message": str(e),
        }
    except httpx.TimeoutException:
        return {
            "error": "Request timeout",
            "message": "The flight search request took too long",
        }
    except httpx.RequestError as e:
        return {
            "error": "Request failed",
            "message": str(e),
        }
    except Exception as e:
        return {
            "error": "Unexpected error",
            "message": str(e),
        }

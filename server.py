#!/usr/bin/env python3
"""Flight Search MCP Server using SearchAPI.io Google Flights API"""

import os
import time
from typing import Optional
from mcp.server.fastmcp import FastMCP
import httpx
import psycopg2
from sentence_transformers import SentenceTransformer

mcp = FastMCP("flight-search")

SEARCHAPI_KEY = os.getenv("SEARCHAPI_KEY", )

# Database connection parameters
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'vectordb',
    'user': 'postgres',
    'password': 'postgres'
}

# Initialize embedding model
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
SEARCHAPI_URL = "https://www.searchapi.io/api/v1/search"


@mcp.tool()
def search_airport(query: str, limit: int = 5) -> dict:
    """Search for airports by name or city using hybrid search (vector + keyword).

    Args:
        query: Airport name or city name to search for (e.g., "Los Angeles", "JFK Airport", "Pearson")
        limit: Maximum number of results to return (default: 5)

    Returns:
        List of matching airports with their codes, names, cities, and countries
    """
    try:
        # Remove "Airport" from query for embedding
        query_for_embedding = query.replace(' Airport', '').replace(' airport', '')
        
        # Generate embedding for the query
        start_time = time.time()
        query_embedding = embedding_model.encode(query_for_embedding).tolist()
        embedding_time = time.time() - start_time
        print(f"Embedding generation took {embedding_time:.4f} seconds")
        
        # Connect to database
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Hybrid search: combine vector similarity with keyword matching
        query_start_time = time.time()
        cursor.execute("""
            WITH keyword_matches AS (
                SELECT 
                    airport_id, name, city, country, iata, icao, tz_database_timezone,
                    1.0 as keyword_score,
                    0 as name_similarity,
                    0 as city_similarity,
                    CASE
                        WHEN UPPER(iata) = UPPER(%s) THEN 'iata'
                        WHEN UPPER(icao) = UPPER(%s) THEN 'icao'
                        WHEN name ILIKE %s THEN 'name_keyword'
                        WHEN city ILIKE %s THEN 'city_keyword'
                    END as match_type
                FROM airports
                WHERE 
                    UPPER(iata) = UPPER(%s)
                    OR UPPER(icao) = UPPER(%s)
                    OR name ILIKE %s
                    OR city ILIKE %s
                LIMIT %s
            ),
            name_matches AS (
                SELECT 
                    airport_id, name, city, country, iata, icao, tz_database_timezone,
                    0 as keyword_score,
                    1 - (name_vector <=> %s::vector) as name_similarity,
                    0 as city_similarity,
                    'name_vector' as match_type
                FROM airports
                WHERE name_vector IS NOT NULL
                ORDER BY name_vector <=> %s::vector
                LIMIT %s
            ),
            city_matches AS (
                SELECT 
                    airport_id, name, city, country, iata, icao, tz_database_timezone,
                    0 as keyword_score,
                    0 as name_similarity,
                    1 - (city_vector <=> %s::vector) as city_similarity,
                    'city_vector' as match_type
                FROM airports
                WHERE city_vector IS NOT NULL
                ORDER BY city_vector <=> %s::vector
                LIMIT %s
            ),
            combined AS (
                SELECT * FROM keyword_matches
                UNION ALL
                SELECT * FROM name_matches
                UNION ALL
                SELECT * FROM city_matches
            )
            SELECT 
                airport_id, name, city, country, iata, icao, tz_database_timezone,
                MAX(keyword_score) as keyword_score,
                MAX(name_similarity) as name_sim,
                MAX(city_similarity) as city_sim,
                GREATEST(MAX(keyword_score), MAX(name_similarity), MAX(city_similarity)) as best_score,
                (array_agg(match_type ORDER BY 
                    CASE match_type
                        WHEN 'iata' THEN 1
                        WHEN 'icao' THEN 2
                        WHEN 'name_keyword' THEN 3
                        WHEN 'city_keyword' THEN 4
                        WHEN 'name_vector' THEN 5
                        WHEN 'city_vector' THEN 6
                    END
                ))[1] as primary_match_type
            FROM combined
            GROUP BY airport_id, name, city, country, iata, icao, tz_database_timezone
            ORDER BY best_score DESC
            LIMIT %s;
        """, (
            query, query, f'%{query}%', f'%{query}%',
            query, query, f'%{query}%', f'%{query}%', limit * 2,
            query_embedding, query_embedding, limit * 2,
            query_embedding, query_embedding, limit * 2,
            limit
        ))
        query_time = time.time() - query_start_time
        print(f"pgvector query took {query_time:.4f} seconds")
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "airport_id": row[0],
                "name": row[1],
                "city": row[2],
                "country": row[3],
                "iata": row[4],
                "icao": row[5],
                "timezone": row[6],
                "similarity_score": round(row[10], 4),
                "matched_by": row[11]  # primary_match_type from query
            })
        
        cursor.close()
        conn.close()
        
        return {
            "query": query,
            "results_count": len(results),
            "airports": results,
            "timing": {
                "embedding_ms": round(embedding_time * 1000, 2),
                "query_ms": round(query_time * 1000, 2),
                "total_ms": round((embedding_time + query_time) * 1000, 2)
            }
        }
        
    except Exception as e:
        return {
            "error": "Search failed",
            "message": str(e)
        }


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


if __name__ == "__main__":
    try:
        mcp.run()
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
# Flight Search MCP Server

A FastMCP server that enables AI assistants to search for flights between airports using the SearchAPI.io Google Flights API. Get real-time flight prices, schedules, airlines, and carbon emissions data through a simple MCP tool interface.

## Setup

1. Create and activate virtual environment:
```bash
uv venv
source .venv/bin/activate
```

2. Install dependencies:
```bash
uv add fastmcp httpx
```

3. Set your API key (optional, defaults to the one provided):
```bash
export SEARCHAPI_KEY="your_api_key_here"
```

## Usage

Test with FastMCP dev mode:
```bash
fastmcp dev server.py
```

Or run directly:
```bash
fastmcp run server.py
```

## Available Tools

### search_flights

Search for flights between airports with specified dates.

**Parameters:**
- `departure_id` (required): Departure airport code (e.g., JFK, LAX)
- `arrival_id` (required): Arrival airport code (e.g., MAD, LHR)
- `outbound_date` (required): Outbound date in YYYY-MM-DD format
- `return_date` (optional): Return date in YYYY-MM-DD format
- `flight_type` (optional): "round_trip" or "one_way" (default: round_trip)

**Example:**
```json
{
  "departure_id": "JFK",
  "arrival_id": "MAD",
  "outbound_date": "2025-11-02",
  "return_date": "2025-11-09",
  "flight_type": "round_trip"
}
```

## MCP Configuration

Add to your `.kiro/settings/mcp.json`:
```json
{
  "mcpServers": {
    "flight-search": {
      "command": "python",
      "args": ["/absolute/path/to/server.py"],
      "env": {
        "SEARCHAPI_KEY": "your_api_key_here"
      }
    }
  }
}
```

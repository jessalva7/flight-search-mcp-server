import csv
import psycopg2
from psycopg2.extras import execute_values
from sentence_transformers import SentenceTransformer

# Database connection parameters
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'vectordb',
    'user': 'postgres',
    'password': 'postgres'
}

# Initialize embedding model
print("Loading embedding model...")
model = SentenceTransformer('all-MiniLM-L6-v2')
EMBEDDING_DIM = 384  # Dimension for all-MiniLM-L6-v2

def create_table(cursor):
    """Create airports table with pgvector extension"""
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    
    cursor.execute(f"""
        DROP TABLE IF EXISTS airports;
        CREATE TABLE airports (
            airport_id INTEGER PRIMARY KEY,
            name TEXT,
            city TEXT,
            country TEXT,
            iata TEXT,
            icao TEXT,
            tz_database_timezone TEXT,
            type TEXT,
            source TEXT,
            name_vector vector({EMBEDDING_DIM}),
            city_vector vector({EMBEDDING_DIM})
        );
    """)
    print("Table created successfully with vector columns")

def load_csv_data(cursor, csv_file):
    """Load data from CSV file into database with embeddings"""
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = []
        names = []
        cities = []
        
        print("Reading CSV data...")
        for row in reader:
            name = row['Name']
            city = row['City']
            
            # Remove "Airport" from name for embedding
            name_for_embedding = name.replace(' Airport', '').replace(' airport', '')
            
            rows.append((
                int(row['Airport ID']),
                name,
                city,
                row['Country'],
                row['IATA'] if row['IATA'] != '\\N' else None,
                row['ICAO'] if row['ICAO'] != '\\N' else None,
                row['Tz database timezone'],
                row['Type'],
                row['Source']
            ))
            names.append(name_for_embedding)
            cities.append(city)
    
    print(f"Generating embeddings for {len(rows)} airports...")
    name_embeddings = model.encode(names, show_progress_bar=True)
    city_embeddings = model.encode(cities, show_progress_bar=True)
    
    print("Inserting data into database...")
    # Combine rows with embeddings
    rows_with_vectors = [
        row + (name_emb.tolist(), city_emb.tolist())
        for row, name_emb, city_emb in zip(rows, name_embeddings, city_embeddings)
    ]
    
    execute_values(
        cursor,
        """
        INSERT INTO airports (
            airport_id, name, city, country, iata, icao,
            tz_database_timezone, type, source, name_vector, city_vector
        ) VALUES %s
        """,
        rows_with_vectors
    )
    print(f"Loaded {len(rows)} airports with embeddings into database")

def main():
    """Main function to load airport data"""
    try:
        # Connect to database
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Create table
        create_table(cursor)
        
        # Load data
        load_csv_data(cursor, 'airport_dataset/airports.csv')
        
        # Commit changes
        conn.commit()
        
        # Verify data
        cursor.execute("SELECT COUNT(*) FROM airports;")
        count = cursor.fetchone()[0]
        print(f"Total airports in database: {count}")
        
        # Show sample data
        cursor.execute("SELECT airport_id, name, city, country FROM airports LIMIT 5;")
        print("\nSample data:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]}, {row[2]}, {row[3]}")
        
        # Create indexes for vector similarity search
        print("\nCreating vector indexes...")
        cursor.execute("CREATE INDEX ON airports USING ivfflat (name_vector vector_cosine_ops) WITH (lists = 100);")
        cursor.execute("CREATE INDEX ON airports USING ivfflat (city_vector vector_cosine_ops) WITH (lists = 100);")
        conn.commit()
        print("Vector indexes created successfully")
        
        cursor.close()
        conn.close()
        print("\nData loaded successfully!")
        
    except Exception as e:
        print(f"Error: {e}")
        if conn:
            conn.rollback()

if __name__ == "__main__":
    main()

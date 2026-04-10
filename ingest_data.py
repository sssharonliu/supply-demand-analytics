import pandas as pd
from sqlalchemy import create_engine
import os

# Set the working directory to prevent path errors
os.chdir(os.path.dirname(os.path.abspath(__file__)))

def run_ingestion():
    try:
        # 1. Read data from the raw folder
        print("📖 Reading DataCo dataset (this may take a few seconds)...")
        df = pd.read_csv('data/raw/DataCoSupplyChainDataset.csv', encoding='latin-1')

        # 2. Clean column names (lowercase, replace spaces/dashes with underscores)
        df.columns = [c.lower().replace(' ', '_').replace('(', '').replace(')', '').replace('-', '_') for c in df.columns]
        
        # 3. Connect to MySQL
        print("🔌 Connecting to MySQL database...")
        user = 'root'
        password = 'password123' 
        host = 'localhost'
        db = 'supply_chain_db' 
        /usr/local/bin/python3 ingest_data.py
        engine = create_engine(f"mysql+pymysql://{user}:{password}@{host}/{db}")

        # 4. Push DataFrame to MySQL
        print("🚀 Pushing 180K rows to MySQL (this will take 1-2 minutes)...")
        df.to_sql('orders', con=engine, if_exists='replace', index=False)
        
        print("✅ SUCCESS! Data ingested perfectly!")

    except Exception as e:
        print(f"❌ Error occurred: {e}")

if __name__ == "__main__":
    run_ingestion()
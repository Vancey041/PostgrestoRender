import os
import pandas as pd
from sqlalchemy import create_engine
import numpy as np

# ==========================================
# 0. DATABASE CONNECTION SETUP
# ==========================================
# Render will securely pass this URL to the script
db_url = os.environ.get("DATABASE_URL")

# Create the SQLAlchemy engine
engine = create_engine(db_url)


# ==========================================
# 1. EXTRACT (To Staging Area)
# ==========================================
print("Starting Extraction...")

# Mocking the source CSV data (Replace these with pd.read_csv('japan_store.csv') etc.)
japan_data = {
    'transaction_id': ['J001', 'J002', 'J003', 'J004', 'J005'],
    'product': ['Laptop', 'Mouse', 'Keyboard', None, 'Monitor'],
    'price_jpy': [150000, 3000, 7500, 10000, 30000],
    'quantity': [1, 2, 1, 1, np.nan],
    'date': ['2023-10-01', '2023-10-01', '2023-10-02', '2023-10-02', '2023-10-03']
}
myanmar_data = {
    'txn_id': ['M001', 'M002', 'M003', 'M004'],
    'item_name': ['Mouse', 'Monitor', 'Desk', 'Chair'],
    'price_usd': [20.0, 210.0, 150.0, 85.0],
    'qty': [5, 1, 2, 1],
    'txn_date': ['2023-10-01', '2023-10-02', '2023-10-02', '2023-10-03']
}

df_japan_raw = pd.DataFrame(japan_data)
df_myanmar_raw = pd.DataFrame(myanmar_data)

# Load raw data into the Staging layer in PostgreSQL
df_japan_raw.to_sql('staging_japan_store', engine, if_exists='replace', index=False)
df_myanmar_raw.to_sql('staging_myanmar_store', engine, if_exists='replace', index=False)
print("Data loaded to staging tables.")

# ==========================================
# 2. TRANSFORM (Transformation Area)
# ==========================================
print("Starting Transformation...")

# Read from Staging
df_jp_stg = pd.read_sql('SELECT * FROM staging_japan_store', engine)
df_mm_stg = pd.read_sql('SELECT * FROM staging_myanmar_store', engine)

# --- Clean Japan Data ---
# Remove nulls
df_jp_clean = df_jp_stg.dropna().copy()
# Standardize schema to match a global format
df_jp_clean = df_jp_clean.rename(columns={
    'transaction_id': 'order_id',
    'product': 'product_name',
    'date': 'order_date'
})
# Convert JPY to USD (Assuming conversion rate 1 USD = 150 JPY)
df_jp_clean['price_usd'] = (df_jp_clean['price_jpy'] / 150).round(2)
df_jp_clean['store_location'] = 'Japan'
df_jp_clean['total_sales_usd'] = df_jp_clean['price_usd'] * df_jp_clean['quantity']

# Drop the old currency column to match global schema
df_jp_clean = df_jp_clean[['order_id', 'store_location', 'product_name', 'price_usd', 'quantity', 'total_sales_usd', 'order_date']]

# --- Clean Myanmar Data ---
# Remove nulls
df_mm_clean = df_mm_stg.dropna().copy()
# Standardize schema
df_mm_clean = df_mm_clean.rename(columns={
    'txn_id': 'order_id',
    'item_name': 'product_name',
    'qty': 'quantity',
    'txn_date': 'order_date'
})
df_mm_clean['store_location'] = 'Myanmar'
df_mm_clean['total_sales_usd'] = df_mm_clean['price_usd'] * df_mm_clean['quantity']
df_mm_clean = df_mm_clean[['order_id', 'store_location', 'product_name', 'price_usd', 'quantity', 'total_sales_usd', 'order_date']]

# Write transformed individual tables to database (Optional transformation layer representation)
df_jp_clean.to_sql('transform_japan_store', engine, if_exists='replace', index=False)
df_mm_clean.to_sql('transform_myanmar_store', engine, if_exists='replace', index=False)
print("Data cleaned, standardized, and saved to transformation tables.")

# ==========================================
# 3. LOAD (Presentation Area)
# ==========================================
print("Starting Load to Presentation...")

# Combine datasets
df_global_sales = pd.concat([df_jp_clean, df_mm_clean], ignore_index=True)

# Ensure correct data types
df_global_sales['order_date'] = pd.to_datetime(df_global_sales['order_date'])
df_global_sales['quantity'] = df_global_sales['quantity'].astype(int)

# Load into the Presentation layer
df_global_sales.to_sql('presentation_global_sales', engine, if_exists='replace', index=False)
print("Consolidated data loaded to presentation_global_sales table.")

# ==========================================
# 4. ANALYTICS (Insights)
# ==========================================
print("\n--- Generating Analytics ---")

# Query the presentation layer directly for analytics
df_final = pd.read_sql('SELECT * FROM presentation_global_sales', engine)

# Insight 1: Total Global Revenue
total_revenue = df_final['total_sales_usd'].sum()
print(f"1. Total Global Revenue: ${total_revenue:,.2f}")

# Insight 2: Revenue by Store Location
revenue_by_store = df_final.groupby('store_location')['total_sales_usd'].sum()
best_store = revenue_by_store.idxmax()
print(f"2. Revenue by Store:\n{revenue_by_store.to_string()}\n   -> The top-performing store is {best_store}.")

# Insight 3: Top Selling Product (by quantity)
top_product_qty = df_final.groupby('product_name')['quantity'].sum().idxmax()
top_product_sales = df_final.groupby('product_name')['quantity'].sum().max()
print(f"3. Top Selling Product by Volume: {top_product_qty} ({top_product_sales} units sold)")

# Insight 4: Highest Revenue Generating Product
top_revenue_product = df_final.groupby('product_name')['total_sales_usd'].sum().idxmax()
top_revenue_amount = df_final.groupby('product_name')['total_sales_usd'].sum().max()
print(f"4. Highest Revenue Product: {top_revenue_product} (${top_revenue_amount:,.2f})")

# Insight 5: Average Order Value (AOV)
aov = df_final['total_sales_usd'].mean()
print(f"5. Average Order Value (AOV) across all stores: ${aov:,.2f}")
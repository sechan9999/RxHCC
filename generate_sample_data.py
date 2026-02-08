import pandas as pd
import random
import os

# Create dummy data for testing the replication logic
# We need: beneficiary_id, claim_id, diagnosis_code, service_date

data = {
    'beneficiary_id': [f'BEN{i:03d}' for i in range(100)],
    'claim_id': [f'CLM{i:03d}' for i in range(100)],
    'diagnosis_code': [random.choice(['E11.9', 'E11.42', 'E11.69', 'E11.A', 'G62.9', 'I10', 'E11.21']) for _ in range(100)],
    'service_date': pd.date_range(start='2025-01-01', periods=100).strftime('%Y-%m-%d').tolist()
}

df = pd.DataFrame(data)

# Save as parquet since the pyspark script reads parquet
# We need pyarrow or fastparquet installed. Let's try CSV first if parquet fails, 
# but the script expects parquet. Let's modify script to read CSV for local testing or ensure parquet lib.
# Actually, let's install pyarrow in the background if needed.
# For now, saving as CSV for simplicity and I will update the sagemaker script to read CSV for local test.

output_dir = "rxhcc_sample_data"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

df.to_parquet(f"{output_dir}/sample_claims.parquet", index=False)
print(f"Sample data created at {output_dir}/sample_claims.parquet")

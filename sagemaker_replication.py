from pyspark.sql import SparkSession
from pyspark.sql.functions import col, when, lit
import sys
import os

# Valid ICD-10 Codes for 2026 RxHCC Model (Simplified)
VALID_CODES_2026 = ["E11.9", "E11.42", "E11.69", "E11.A"]

# ---------------------------------------------------------
# SPARK EXECUTION (SageMaker / Cluster)
# ---------------------------------------------------------
def run_spark_job(input_path, output_path):
    print("Attempting to start Spark Session...")
    try:
        spark = SparkSession.builder \
            .appName("RxHCC_Replication_2026") \
            .master("local[*]") \
            .config("spark.driver.bindAddress", "127.0.0.1") \
            .getOrCreate()
        
        print(f"Reading data from {input_path} (Spark)...")
        df_claims = spark.read.parquet(input_path)
        
        df_processed = df_claims.select(
            col("beneficiary_id"),
            col("claim_id"),
            col("diagnosis_code"),
            col("service_date")
        ).distinct()
        
        df_filtered = df_processed.filter(col("diagnosis_code").isin(VALID_CODES_2026))
        
        count = df_filtered.count()
        print(f"Spark: Filtered down to {count} valid 2026 RxHCC related records.")
        df_filtered.show()
        
        print(f"Writing replicated processed data to {output_path}...")
        df_filtered.write.mode("overwrite").partitionBy("diagnosis_code").parquet(output_path)
        print("Spark Job Complete.")
        
    except Exception as e:
        print(f"\n[WARN] Spark Execution Failed: {e}")
        print("[INFO] This is common on Windows if 'winutils.exe' (Hadoop) is missing.")
        print("[INFO] Falling back to Local Pandas Engine for testing...\n")
        run_pandas_fallback(input_path, output_path)

# ---------------------------------------------------------
# PANDAS FALLBACK (Local / Windows Testing)
# ---------------------------------------------------------
def run_pandas_fallback(input_path, output_path):
    import pandas as pd
    import glob
    
    print(f"Reading data from {input_path} (Pandas)...")
    try:
        # Handle directory of parquet files or single file
        if os.path.isdir(input_path):
            files = glob.glob(os.path.join(input_path, "*.parquet"))
            df_claims = pd.concat([pd.read_parquet(f) for f in files])
        else:
            df_claims = pd.read_parquet(input_path)
            
        # Logic Replication
        df_processed = df_claims[['beneficiary_id', 'claim_id', 'diagnosis_code', 'service_date']].drop_duplicates()
        
        df_filtered = df_processed[df_processed['diagnosis_code'].isin(VALID_CODES_2026)]
        
        count = len(df_filtered)
        print(f"Pandas: Filtered down to {count} valid 2026 RxHCC related records.")
        print(df_filtered.head())
        
        # Write Output (Mimic Partitioning)
        if not os.path.exists(output_path):
            os.makedirs(output_path)
            
        # Save partitioned by diagnosis_code
        for diagnosis, group in df_filtered.groupby('diagnosis_code'):
            part_dir = os.path.join(output_path, f"diagnosis_code={diagnosis}")
            if not os.path.exists(part_dir):
                os.makedirs(part_dir)
            group.to_parquet(os.path.join(part_dir, "part-00000.parquet"), index=False)
            
        print(f"Pandas: Output written to {output_path}")
        
    except Exception as e:
        print(f"Pandas Engine Failed: {e}")

def run_replication_job(input_path, output_path):
    """
    Migrated Replication Logic to Amazon SageMaker (PySpark).
    Handles multi-million record processing for Risk Adjustment.
    """
    run_spark_job(input_path, output_path)

if __name__ == "__main__":
    # Local testing paths
    INPUT_PATH = "rxhcc_sample_data/sample_claims.parquet"
    OUTPUT_PATH = "rxhcc_output_data"
    
    # Check if sample data exists
    if not os.path.exists(INPUT_PATH):
        print("Sample data not found. Please run generate_sample_data.py first.")
        sys.exit(1)

    run_spark_job(INPUT_PATH, OUTPUT_PATH)

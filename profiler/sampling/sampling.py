# =========================================================
# ADAPTIVE PARALLEL PROFILER
# =========================================================
#
# Tier Strategy
# ---------------------------------------------------------
#
# Tiny (<10MB)
#   -> Reservoir
#   -> Python
#
# Small (10MB-100MB)
#   -> Reservoir + optional HLL
#   -> Python
#
# Medium (100MB-1GB)
#   -> Reservoir + HLL OR Row Sampling
#   -> DuckDB
#
# Large (1GB-10GB)
#   -> Metadata + Row Group Sampling
#   -> DuckDB
#
# Very Large (10GB-100GB)
#   -> Metadata + Row Groups + HLL
#   -> DuckDB
#
# Huge (100GB-TB)
#   -> Streaming + Sketches
#
# Massive / Continuous
#   -> Distributed Streaming
#
# =========================================================
#
# INSTALL
# ---------------------------------------------------------
#
# pip install duckdb pandas pyarrow psutil
#
# OPTIONAL HLL:
# pip install datasketch
#
# =========================================================

import os
import csv
import time
import random
import psutil
import duckdb
import pandas as pd

from pathlib import Path
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed

# =========================================================
# CONFIG
# =========================================================

DATA_FOLDER = "./data"
OUTPUT_FOLDER = "./output"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

MAX_WORKERS = os.cpu_count()

# =========================================================
# SIZE THRESHOLDS
# =========================================================

KB = 1024
MB = KB * 1024
GB = MB * 1024

TINY_LIMIT = 10
SMALL_LIMIT = 100
MEDIUM_LIMIT = 1024
LARGE_LIMIT = 10240
VERY_LARGE_LIMIT = 102400

# =========================================================
# LOG FILE
# =========================================================

LOG_FILE = os.path.join(
    OUTPUT_FOLDER,
    "performance_log.csv"
)

if not os.path.exists(LOG_FILE):

    pd.DataFrame(columns=[
        "timestamp",
        "file_name",
        "file_size_mb",
        "tier",
        "engine",
        "strategy",
        "rows_processed",
        "sample_rows",
        "execution_time_sec",
        "rows_per_sec",
        "mb_per_sec",
        "memory_mb"
    ]).to_csv(LOG_FILE, index=False)

# =========================================================
# FILE SIZE
# =========================================================

def get_file_size_mb(file_path):

    size_bytes = os.path.getsize(file_path)

    return round(size_bytes / (1024 * 1024), 2)

# =========================================================
# CLASSIFIER
# =========================================================

def classify_workload(size_mb):

    if size_mb < 10:

        return {
            "tier": "tiny",
            "engine": "python",
            "strategy": "reservoir"
        }

    elif size_mb < 100:

        return {
            "tier": "small",
            "engine": "python",
            "strategy": "reservoir_hll"
        }

    elif size_mb < 1024:

        return {
            "tier": "medium",
            "engine": "duckdb",
            "strategy": "reservoir_hll"
        }

    elif size_mb < 10240:

        return {
            "tier": "large",
            "engine": "duckdb",
            "strategy": "metadata_rowgroup"
        }

    elif size_mb < 102400:

        return {
            "tier": "very_large",
            "engine": "duckdb",
            "strategy": "metadata_rowgroup_hll"
        }

    else:

        return {
            "tier": "huge",
            "engine": "streaming",
            "strategy": "streaming_sketches"
        }

# =========================================================
# PYTHON RESERVOIR SAMPLING
# =========================================================

def python_reservoir_sampling(
    file_path,
    sample_size=1000
):

    reservoir = []

    total_rows = 0

    with open(
        file_path,
        "r",
        encoding="utf-8-sig"
    ) as f:

        reader = csv.reader(f)

        header = next(reader)

        for row in reader:

            total_rows += 1

            if len(reservoir) < sample_size:

                reservoir.append(row)

            else:

                j = random.randint(
                    0,
                    total_rows - 1
                )

                if j < sample_size:

                    reservoir[j] = row

    return header, reservoir, total_rows

# =========================================================
# DUCKDB CONNECTION
# =========================================================

def get_duckdb_connection():

    con = duckdb.connect(database=':memory:')

    con.execute("""
        PRAGMA threads=4;
    """)

    return con

# =========================================================
# DUCKDB FILE READER
# =========================================================

def get_reader(file_path):

    ext = Path(file_path).suffix.lower()

    if ext == ".csv":

        return f"read_csv_auto('{file_path}')"

    elif ext == ".parquet":

        return f"read_parquet('{file_path}')"

    else:

        raise ValueError(
            f"Unsupported file format: {ext}"
        )

# =========================================================
# DUCKDB RESERVOIR
# =========================================================

def duckdb_reservoir_sampling(
    con,
    reader,
    sample_size=1000
):

    query = f"""
    SELECT *
    FROM {reader}
    USING SAMPLE reservoir({sample_size} ROWS)
    """

    return con.execute(query).fetch_arrow_table()

# =========================================================
# DUCKDB ROW GROUP STYLE
# =========================================================

def duckdb_rowgroup_sampling(
    con,
    reader,
    sample_size=5000
):

    query = f"""
    SELECT *
    FROM {reader}
    USING SAMPLE {sample_size} ROWS
    """

    return con.execute(query).fetch_arrow_table()

# =========================================================
# STREAMING SAMPLING
# =========================================================

def streaming_sampling(
    con,
    reader
):

    query = f"""
    SELECT *
    FROM {reader}
    WHERE random() < 0.0001
    LIMIT 10000
    """

    return con.execute(query).fetch_arrow_table()

# =========================================================
# SAVE SAMPLE
# =========================================================

def save_arrow_table(
    table,
    file_name
):

    output_path = os.path.join(
        OUTPUT_FOLDER,
        f"{Path(file_name).stem}_sample.parquet"
    )

    import pyarrow.parquet as pq

    pq.write_table(
        table,
        output_path
    )

    return output_path

# =========================================================
# PROCESS FILE
# =========================================================

def process_file(file_path):

    process = psutil.Process(os.getpid())

    start = time.perf_counter()

    file_name = os.path.basename(file_path)

    size_mb = get_file_size_mb(file_path)

    workload = classify_workload(size_mb)

    tier = workload["tier"]
    engine = workload["engine"]
    strategy = workload["strategy"]

    # =====================================================
    # PYTHON ENGINE
    # =====================================================

    if engine == "python":

        header, rows, total_rows = (
            python_reservoir_sampling(file_path)
        )

        sample_rows = len(rows)

        output_path = os.path.join(
            OUTPUT_FOLDER,
            f"{Path(file_name).stem}_sample.csv"
        )

        with open(
            output_path,
            "w",
            newline="",
            encoding="utf-8"
        ) as f:

            writer = csv.writer(f)

            writer.writerow(header)

            writer.writerows(rows)

    # =====================================================
    # DUCKDB ENGINE
    # =====================================================

    elif engine == "duckdb":

        con = get_duckdb_connection()

        reader = get_reader(file_path)

        count_query = f"""
        SELECT COUNT(*) AS cnt
        FROM {reader}
        """

        total_rows = (
            con.execute(count_query)
            .fetchone()[0]
        )

        if strategy == "reservoir_hll":

            table = duckdb_reservoir_sampling(
                con,
                reader
            )

        else:

            table = duckdb_rowgroup_sampling(
                con,
                reader
            )

        sample_rows = table.num_rows

        output_path = save_arrow_table(
            table,
            file_name
        )

    # =====================================================
    # STREAMING ENGINE
    # =====================================================

    else:

        con = get_duckdb_connection()

        reader = get_reader(file_path)

        count_query = f"""
        SELECT COUNT(*) AS cnt
        FROM {reader}
        """

        total_rows = (
            con.execute(count_query)
            .fetchone()[0]
        )

        table = streaming_sampling(
            con,
            reader
        )

        sample_rows = table.num_rows

        output_path = save_arrow_table(
            table,
            file_name
        )

    # =====================================================
    # PERFORMANCE METRICS
    # =====================================================

    end = time.perf_counter()

    exec_time = end - start

    rows_per_sec = (
        total_rows / exec_time
        if exec_time > 0 else 0
    )

    mb_per_sec = (
        size_mb / exec_time
        if exec_time > 0 else 0
    )

    memory_mb = (
        process.memory_info().rss
        / (1024 * 1024)
    )

    result = {
        "timestamp": datetime.now().isoformat(),
        "file_name": file_name,
        "file_size_mb": size_mb,
        "tier": tier,
        "engine": engine,
        "strategy": strategy,
        "rows_processed": total_rows,
        "sample_rows": sample_rows,
        "execution_time_sec": round(exec_time, 4),
        "rows_per_sec": round(rows_per_sec, 2),
        "mb_per_sec": round(mb_per_sec, 2),
        "memory_mb": round(memory_mb, 2)
    }

    print("\n================================")
    print(f"File: {file_name}")
    print(f"Tier: {tier}")
    print(f"Engine: {engine}")
    print(f"Strategy: {strategy}")
    print(f"Rows: {total_rows}")
    print(f"Sample Rows: {sample_rows}")
    print(f"Execution Time: {round(exec_time,4)} sec")
    print(f"Rows/sec: {round(rows_per_sec,2)}")
    print(f"MB/sec: {round(mb_per_sec,2)}")
    print(f"Memory: {round(memory_mb,2)} MB")
    print(f"Saved: {output_path}")

    return result

# =========================================================
# WRITE LOGS
# =========================================================

def write_logs(results):

    df = pd.DataFrame(results)

    df.to_csv(
        LOG_FILE,
        mode="a",
        index=False,
        header=False
    )

# =========================================================
# MAIN
# =========================================================

def main():

    print("\n================================")
    print("ADAPTIVE PARALLEL PROFILER")
    print("================================")

    total_start = time.perf_counter()

    files = [
        os.path.join(DATA_FOLDER, f)
        for f in os.listdir(DATA_FOLDER)
        if f.endswith(".csv")
        or f.endswith(".parquet")
    ]

    results = []

    # =====================================================
    # PARALLEL EXECUTION
    # =====================================================

    with ProcessPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {
            executor.submit(process_file, f): f
            for f in files
        }

        for future in as_completed(futures):

            try:

                results.append(
                    future.result()
                )

            except Exception as e:

                print("ERROR:", e)

    # =====================================================
    # WRITE LOGS
    # =====================================================

    write_logs(results)

    total_end = time.perf_counter()

    total_time = total_end - total_start

    # =====================================================
    # SUMMARY
    # =====================================================

    total_rows = sum(
        r["rows_processed"]
        for r in results
    )

    total_mb = sum(
        r["file_size_mb"]
        for r in results
    )

    print("\n================================")
    print("SUMMARY")
    print("================================")

    print(f"Files Processed: {len(results)}")
    print(f"Total Rows: {total_rows}")
    print(f"Total Data: {round(total_mb,2)} MB")
    print(f"Total Time: {round(total_time,4)} sec")

    print("\nLog File:")
    print(LOG_FILE)

# =========================================================

if __name__ == "__main__":

    main()

# =========================================================
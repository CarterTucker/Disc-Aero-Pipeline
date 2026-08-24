import run_case_v1 as oCFD
import csv
import time
from pathlib import Path
import subprocess
import os

def check_no_stale_processes():
    result = subprocess.run(
        ["pgrep", "-f", "foamRun|mpirun|decomposePar"],
        capture_output=True, text=True
    )
    if result.stdout.strip():
        raise RuntimeError(
            "Stale OpenFOAM/MPI processes detected — kill them before starting a new sweep.\n"
            f"PIDs found:\n{result.stdout}"
        )

FILENAME = 'OverstableApproachDisc.stl'
geometry = oCFD.get_stl_dimensions(FILENAME)

check_no_stale_processes()
oCFD.initialize()
mesh_dir = oCFD.mesh_stl(FILENAME, geometry)   # capture the return value

aoa_list = [-10, -5, -2.5, 0, 2.5, 5, 7.5, 10, 12.5, 15, 20, 25]
beta_list = [-15, -10, -5, 0, 5, 10, 15]
velo_list = [8, 14, 20, 26, 30]

headers = ['AoA', 'Beta', 'U', 'CD', 'CL', 'Cm', 'Cl_roll', 'Cn_yaw', 'elapsed_sec']
results_path = Path('output.csv')
write_header = not results_path.exists()

completed = set()
csv_path = "/home/ctucker4/disc-aero-pipeline/scripts/output.csv"

if os.path.exists(csv_path):
    with open(csv_path, "r") as f:
        reader = csv.reader(f)
        for row in reader:
            if row and not row[0].startswith("#"):  # skip header/comments if any
                aoa, beta, U = row[0], row[1], row[2]
                completed.add((aoa, beta, U))

with open(results_path, 'a', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    if write_header:
        writer.writerow(headers)

    total = len(aoa_list) * len(velo_list) * len(beta_list)
    count = 0

    for aoa in aoa_list:
        for beta in beta_list:
            for velo in velo_list:
                key = (str(aoa), str(beta), str(velo))
                if key in completed:
                    print(f"Skipping trial: AoA={aoa}, beta={beta}, U={U} (already in output.csv)")
                    count += 1
                    continue
                count += 1
                print(f"\n=== Run {count}/{total}: AoA={aoa}, U={velo} ===")

                oCFD.reset_flow_conditions()

                start = time.time()
                try:
                    run_results = oCFD.single_case(geometry, aoa_deg=aoa, beta_deg=beta, velocity=velo)
                    elapsed = time.time() - start
                    row = [aoa, beta, velo, run_results['CD'], run_results['CL'], run_results['Cm'],
                        run_results['Cl_roll'], run_results['Cn_yaw'], round(elapsed, 1)]
                    print(f"  -> CD={run_results['CD']:.4f}  CL={run_results['CL']:.4f}  "
                        f"Cm={run_results['Cm']:.4f}  Cl_roll={run_results['Cl_roll']:.4f}  "
                        f"Cn_yaw={run_results['Cn_yaw']:.4f}")
                except Exception as e:
                    elapsed = time.time() - start
                    print(f"  FAILED: {e}")
                    row = [aoa, beta, velo, None, None, None, None, None, round(elapsed, 1)]

                writer.writerow(row)
                file.flush()

print(f"\nSweep complete. Results in {results_path}")
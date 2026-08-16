import run_case_v1 as oCFD
import csv
import time
from pathlib import Path

FILENAME = 'YOUR_STL_HERE.stl'
geometry = oCFD.get_stl_dimensions(FILENAME)

oCFD.initialize()
mesh_dir = oCFD.mesh_stl(FILENAME, geometry)   # capture the return value

aoa_list = [-10, -5, -2.5, 0, 2.5, 5, 7.5, 10, 12.5, 15, 20, 25]
velo_list = [8, 14, 20, 26, 30]

headers = ['AoA', 'U', 'Cd', 'Cl', 'Cm', 'elapsed_sec']
results_path = Path('output.csv')
write_header = not results_path.exists()

with open(results_path, 'a', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    if write_header:
        writer.writerow(headers)

    total = len(aoa_list) * len(velo_list)
    count = 0

    for aoa in aoa_list:
        for velo in velo_list:
            count += 1
            print(f"\n=== Run {count}/{total}: AoA={aoa}, U={velo} ===")

            oCFD.reset_flow_conditions()

            start = time.time()
            try:
                run_results = oCFD.single_case(geometry, aoa_deg=aoa, velocity=velo)
                elapsed = time.time() - start
                row = [aoa, velo, run_results['Cd'], run_results['Cl'], run_results['CmPitch'], round(elapsed, 1)]
                print(f"  -> Cd={run_results['Cd']:.4f}  Cl={run_results['Cl']:.4f}  Cm={run_results['CmPitch']:.4f}")
            except Exception as e:
                elapsed = time.time() - start
                print(f"  FAILED: {e}")
                row = [aoa, velo, None, None, None, round(elapsed, 1)]

            writer.writerow(row)
            file.flush()

print(f"\nSweep complete. Results in {results_path}")
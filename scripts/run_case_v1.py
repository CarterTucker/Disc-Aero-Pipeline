from pathlib import Path
from stl import mesh as stl_mesh
import math
import shutil
import subprocess


REPO_ROOT = Path(__file__).resolve().parent.parent      # disc-aero-pipeline folder directory
CASE_TEMPLATE = REPO_ROOT / "case_template"             # case template folder directory
CASE_DIR = REPO_ROOT / "run" / "temp"
MESH_DIR = REPO_ROOT / "run" / "temp" / "constant" / "triSurface"
STL_DIR = REPO_ROOT / "disc_database"
LOG_DIR = CASE_DIR / "logs"


def get_stl_dimensions(stl_path: Path, units_scale: float = 0.001, density: float = 950.0):
    """
    INPUT: STL path
    OUTPUT: Disc diameter, planform area, bounding box dimensions, centroid location, mass, Izz, and Ixx

    """

    # retrieve STL and mesh from file, and scale from mm to m
    m = stl_mesh.Mesh.from_file(STL_DIR / stl_path)
    m.vectors *= units_scale
    pts = m.vectors.reshape(-1, 3)

    # find the edge points of the disc, determine disc bounding box and centroid location
    mins = pts.min(axis=0)
    maxs = pts.max(axis=0)
    dims = maxs - mins
    centroid = (mins + maxs) / 2.0

    # find the diameter from the bounding box
    diameter = max(dims[0], dims[1])          # max argument prevents the width of the disc from being taken as the diameter
    area = math.pi * (diameter / 2.0) **2

    # find the mass properties
    volume, cog, inertia = m.get_mass_properties()
    mass = volume * density

    # take the significant inertia (axial symmetry)
    Izz = inertia[2, 2]
    Ixx = inertia[0, 0]

    # return dimensions
    return {"diameter": diameter, "area": area, "dims": dims, "centroid": centroid, "mass": mass, "Izz": Izz, "Ixx": Ixx}


def initialize():
    """
    FUNCTION: Deletes any old case conditions from the temp folder if they exist.

    """
    if CASE_DIR.exists():
        shutil.rmtree(CASE_DIR)

    shutil.copytree(CASE_TEMPLATE, CASE_DIR)

    LOG_DIR.mkdir()


def write_velocity_bc(case_dir: Path, U: float, aoa_deg: float):
    """
    INPUT: case directory, flow velocity, angle of attack
    FUNCTION: Rewrites the 0/U file to run the test

    """

    # reconstruct the normal straight flow velocity into vertical and horizontal components
    aoa_rad= math.radians(aoa_deg)
    ux = U*math.cos(aoa_rad)
    uz = U*math.sin(aoa_rad)
    vec = f"({ux:.6f} 0 {uz:.6f})"

    # rewrite the velocity field in U
    u_file = case_dir / "0" / "U"
    text = u_file.read_text()
    text = text.replace("uniform (20 0 0)", f"uniform {vec}")
    u_file.write_text(text)


def write_force_coeffs(case_dir: Path, U: float, aoa_deg: float, area: float, length: float, centroid):
    """
    INPUT: case directory, flow velocity, planform area, diameter, centroid location
    FUNCTION: Rewrites the system/forceCoeffs1 file to run the specified case conditions
    
    """

    # redefine lift and drag vectors, and store it in the forceCoeffs1 function
    aoa_rad = math.radians(aoa_deg)
    drag_dir = (math.cos(aoa_rad), 0.0, math.sin(aoa_rad))
    lift_dir = (-math.sin(aoa_rad), 0.0, math.cos(aoa_rad))

    fc_file = case_dir / "system" / "forceCoeffs1"
    text = fc_file.read_text()

    text = text.replace("liftDir         (0 0 1);", f"liftDir         ({lift_dir[0]:.6f} {lift_dir[1]:.6f} {lift_dir[2]:.6f});",)
    text = text.replace("dragDir         (1 0 0);", f"dragDir         ({drag_dir[0]:.6f} {drag_dir[1]:.6f} {drag_dir[2]:.6f});",)

    # store the new disc geometry, velocity field, and centroid 
    text = text.replace("magUInf         20.0;", f"magUInf         {U:.6f};",)
    text = text.replace("Aref            0.0316;", f"Aref            {area:.6f};",)
    text = text.replace("lRef            0.2006;", f"lRef            {length:.6f};",)
    text = text.replace("CofR            (0 0 0.01);", f"CofR            ({centroid[0]:.6f} {centroid[1]:.6f} {centroid[2]:.6f});",)

    fc_file.write_text(text)


def write_location_in_mesh(case_dir: Path, D: float):
    """
    INPUT: case directory, disc diameter
    FUNCTION: Rewrites the system/snappyHexMeshDict file to identify the outside of the disc via point outside the disc

    """
    y_offset = 2.0*D
    point = f"(0.0 {y_offset:.4f} 0.0)"

    dict_file = case_dir / "system" / "snappyHexMeshDict"
    text = dict_file.read_text()
    text = text.replace("locationInMesh (0.0 0.4011 0.0);", f"locationInMesh {point};")
    dict_file.write_text(text)


def run_cmd(cmd, cwd, log_path):
    """
    INPUT: case command (with options), case directory, and log path
    FUNCTION: runs the command in WSL

    """
    # run the command above and records the output to a path to result log
    with open(log_path, "w") as logf:
        result = subprocess.run(
            cmd, cwd=cwd, shell=True, stdout=logf, stderr=subprocess.STDOUT
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {result.returncode}): {cmd}\nSee log: {log_path}"
        )


def mesh_stl(stl_path: Path, geometry: dict, stl_units_mm=True, mesh_name=None):
    """
    INPUT: case directory
    FUNCTION: completes meshing and mesh fixing
    
    """
    stl_path = Path(STL_DIR / stl_path).resolve()

    if not stl_path.exists():
        raise FileNotFoundError(f"STL not found: {stl_path}")

    units_scale = 0.001 if stl_units_mm else 1.0

    if any(Path(MESH_DIR).iterdir()):
        shutil.rmtree(MESH_DIR)
        MESH_DIR.mkdir()

    shutil.copy(stl_path, MESH_DIR / "disc.stl")
    subprocess.run(
        ["surfaceTransformPoints", f"scale=({units_scale} {units_scale} {units_scale})",
         str(MESH_DIR / "disc.stl"), str(MESH_DIR / "disc.stl")],
        check=True,
    )

    write_location_in_mesh(CASE_DIR, geometry["diameter"])

    print("Initiate blockMesh ...")
    run_cmd("blockMesh", CASE_DIR, LOG_DIR / "blockMesh.log")
    print("COMPLETE\n")

    print("Initiate snappyHexMesh ...")
    run_cmd("snappyHexMesh -overwrite", CASE_DIR, LOG_DIR / "snappyHexMesh.log")
    print("COMPLETE\n")


def reset_flow_conditions():
    """
    Restores the flow conditions so that the write_... functions work correctly.
    """
    shutil.copy(CASE_TEMPLATE / "0" / "U", CASE_DIR / "0" / "U")
    shutil.copy(CASE_TEMPLATE / "system" / "forceCoeffs1", CASE_DIR / "system" / "forceCoeffs1")


def decompose_and_run_parallel(case_dir: Path, n_procs: int = 10):
    """Splits the mesh into n_procs pieces, solves in parallel via MPI,
    then reconstructs results back into a single case."""

    print(f"Decomposing mesh into {n_procs} subdomains ...")
    run_cmd("decomposePar -force", case_dir, LOG_DIR / "decomposePar.log")

    print(f"Running foamRun in parallel ({n_procs} processes) ...")
    run_cmd(
        f"mpirun --mca btl_vader_single_copy_mechanism none -np {n_procs} foamRun -solver incompressibleFluid -parallel",
        case_dir,
        LOG_DIR / "foamRun.log",
    )

    print("Reconstructing results ...")
    run_cmd("reconstructPar -latestTime", case_dir, LOG_DIR / "reconstructPar.log")


def parse_force_coeffs(case_dir: Path):

    # opens the coefficients data file OpenFOAM dumps to
    postproc_dir = case_dir / "postProcessing" / "forceCoeffs1" / "0"
    dat_file = postproc_dir / "forceCoeffs.dat"

    if not dat_file.exists():
        raise FileNotFoundError(
            f"No forceCoeffs output found at {dat_file}. "
            f"Check logs/foamRun.log"
        )

    lines = [l for l in dat_file.read_text().splitlines() if l and not l.startswith("#")]
    if not lines:
        raise RuntimeError(f"{dat_file} has no data rows.")

    header_line = [l for l in dat_file.read_text().splitlines() if l.startswith("# Time")]
    if not header_line:
        raise RuntimeError(f"Could not find header row in {dat_file}")
    headers = header_line[0].lstrip("#").split()

    # reads the last line and extracts the force coeffs
    last = lines[-1].split()
    values = dict(zip(headers, last))
    return {
        "Cd": float(values["Cd"]),
        "Cl": float(values["Cl"]),
        "CmPitch": float(values.get("Cm", values.get("CmPitch", "nan"))),
    }


def single_case(geometry: dict, aoa_deg: float = 0.0, velocity: float = 25.0, disc_density: float = 950, run_name=None):
    """
    INPUT: 
    FUNCTION: 

    """
    mesh_path = Path(MESH_DIR / "disc.stl").resolve()
    if not mesh_path.exists():
        raise FileNotFoundError(f"Mesh not found: {mesh_path}")

    write_velocity_bc(CASE_DIR, velocity, aoa_deg)
    write_force_coeffs(CASE_DIR, velocity, aoa_deg, geometry["area"], geometry["diameter"], geometry["centroid"])
    write_location_in_mesh(CASE_DIR, geometry["diameter"])

    print(f"Running pipeline: AoA={aoa_deg} deg, U={velocity} m/s ...")

    # run_cmd("foamRun -solver incompressibleFluid", CASE_DIR, LOG_DIR / "foamRun.log")
    decompose_and_run_parallel(CASE_DIR, n_procs=10)

    coeffs = parse_force_coeffs(CASE_DIR)
    print(f"COMPLETE (Cd={coeffs['Cd']:.4f}  Cl={coeffs['Cl']:.4f}  CmPitch={coeffs['CmPitch']:.4f}\n")
    return {"run_name": run_name, "aoa_deg": aoa_deg, "velocity": velocity, **coeffs}

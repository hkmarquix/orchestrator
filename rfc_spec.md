## Sprint Contract: Simple Python Hello World Program

### Objective

Provide one minimal Python CLI example that lets a user verify that Python is
installed correctly and that a script can be run from the command line.

### In Scope

- Add one file named `hello.py` at the repository root.
- Implement a single command-line program that prints `Hello, world!` followed
  by a newline.
- Ensure the program is runnable with `python3 hello.py` from the directory
  containing `hello.py`.

### Out of Scope

- Any file other than `hello.py`
- GUI behavior
- Command-line argument parsing
- Interactive input
- Configuration files or configuration loading
- Environment-variable-dependent behavior
- Logging, banners, prompts, or extra console text
- Packaging, publishing, containerization, installation scripts, or virtual
  environment setup
- Third-party dependencies

### Deliverable

The sprint is complete only if all of the following are true:

1. A file named `hello.py` exists at the repository root.
2. `hello.py` is sufficient on its own to satisfy this contract.
3. No additional files are added or required for execution.

### Implementation Requirements

1. The implementation must be compatible with Python 3.9 and newer.
2. The implementation must run as a single file.
3. The implementation must not require installation of any third-party package.
4. The implementation may use only the Python standard library.
5. The implementation must not import or require any third-party package.
6. The implementation must not parse command-line arguments.
7. The implementation must not read from standard input.
8. The implementation must not prompt, pause, wait for user input, or open a
   GUI.
9. The implementation must not load configuration from files or environment
   variables.
10. The implementation must not print any text other than the required output.

### Required CLI Behavior

1. The required invocation is `python3 hello.py`.
2. The command must be run from the directory containing `hello.py`.
3. The program must require no flags, arguments, installation steps, packaging
   steps, or setup steps beyond having `python3` available.
4. Acceptance is defined only for the required invocation in item 1. Behavior
   for any other invocation is out of scope.

### Required Runtime Behavior

1. On success, the process must exit with status code `0`.
2. Standard output must be exactly `Hello, world!\n`, byte-for-byte.
3. Standard error must be empty.
4. Execution must complete without reading from standard input.
5. Execution must complete without prompts, banners, logging lines, warnings,
   or tracebacks.

### Acceptance Preconditions

Acceptance testing applies only if the following precondition is met:

1. Running `python3 --version` reports Python 3.9 or newer.

### Mandatory Acceptance Test Plan

Run the following commands from the repository root.

1. Verify the Python version precondition:

```sh
python3 --version
```

Pass condition: the reported version is Python 3.9 or newer.

2. Verify the exact program behavior:

```sh
python3 hello.py >stdout.txt 2>stderr.txt
status=$?
printf '%s' "$status" >exit_code.txt
```

Pass conditions:

- `exit_code.txt` contains exactly `0`
- `stderr.txt` is empty
- `stdout.txt` contains exactly `Hello, world!\n`

3. Verify stdout exactly:

```sh
python3 - <<'PY'
from pathlib import Path
data = Path("stdout.txt").read_bytes()
assert data == b"Hello, world!\n", data
PY
```

Pass condition: the command exits with status code `0`.

4. Verify stderr is empty:

```sh
python3 - <<'PY'
from pathlib import Path
data = Path("stderr.txt").read_bytes()
assert data == b"", data
PY
```

Pass condition: the command exits with status code `0`.

5. Verify exit code exactly:

```sh
python3 - <<'PY'
from pathlib import Path
data = Path("exit_code.txt").read_text()
assert data == "0", data
PY
```

Pass condition: the command exits with status code `0`.

### Success Criteria

This sprint is accepted only if all of the following are true:

1. The deliverable matches the defined file name and location.
2. The implementation stays within the stated scope boundaries.
3. The implementation satisfies all implementation requirements.
4. The required invocation behaves exactly as specified.
5. Every step in the mandatory acceptance test plan passes.
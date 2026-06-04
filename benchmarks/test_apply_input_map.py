import timeit
import sys

setup_code = """
input_map = {f"k{i}": f"v{i}" for i in range(100)}
input_map.update({f"i{i}": i for i in range(100)})
input_map.update({"complex1": {"a": "b"}, "complex2": ["x", "y"]})
accumulated = {f"v{i}": f"val{i}" for i in range(50)}

def original():
    resolved = {}
    for target_field, source in input_map.items():
        if isinstance(source, str) and source in accumulated:
            resolved[target_field] = accumulated[source]
        else:
            resolved[target_field] = source
    return resolved

def optimized():
    return {
        target_field: accumulated[source] if type(source) is str and source in accumulated else source
        for target_field, source in input_map.items()
    }
"""

def main():
    print("Running benchmarks...")
    original_time = timeit.timeit("original()", setup=setup_code, number=100000)
    optimized_time = timeit.timeit("optimized()", setup=setup_code, number=100000)

    print(f"Original Time:  {original_time:.5f}s")
    print(f"Optimized Time: {optimized_time:.5f}s")

    improvement = (original_time - optimized_time) / original_time * 100
    print(f"Improvement:    {improvement:.2f}%")

    # Save results to a file so we can include them in the PR description
    with open("benchmarks/results.txt", "w") as f:
        f.write(f"Original Time:  {original_time:.5f}s\n")
        f.write(f"Optimized Time: {optimized_time:.5f}s\n")
        f.write(f"Improvement:    {improvement:.2f}%\n")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Example SST Configuration File

This is a simple example that demonstrates basic SST setup.
Replace this with your actual SST simulation configuration.
"""

import sst

# Define simulation parameters
clock = "1GHz"
memory_size = "1GB"

# Create components (example - replace with your actual components)
print("SST Example Configuration")
print("=" * 50)
print(f"Clock frequency: {clock}")
print(f"Memory size: {memory_size}")
print("=" * 50)

# Example: Create a simple component
# Uncomment and modify based on your actual SST elements
# comp = sst.Component("example_component", "example.component")
# comp.addParams({
#     "clock": clock,
# })

# Set statistics output
sst.setStatisticLoadLevel(5)
sst.setStatisticOutput("sst.statOutputConsole")

print("\nConfiguration loaded successfully!")
print("Note: This is an example. Replace with your actual SST configuration.")

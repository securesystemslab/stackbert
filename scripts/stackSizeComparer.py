import argparse
import json
import os
import logging

parser = argparse.ArgumentParser(description="Compare stack sizes for the same binary collected from two different sources")
parser.add_argument("--other", metavar="F",
        type=str, help="Location of first json")
parser.add_argument("--binrec", metavar="S",
        type=str, help="Location of second json")
args = parser.parse_args()

logging.basicConfig(level=logging.WARN)

if __name__ == "__main__":
    first = json.load(open(args.other, "r"))
    binrec = json.load(open(args.binrec, "r"))

    second = {}

    for key in binrec["stackSizes"]:
        second[key.split("Func_")[1]] = binrec["stackSizes"][key]

    for first_key in first:
       if first_key not in second:
           logging.info(f"{first_key} not in binrec result")
           continue

       if first[first_key]["max"] != second[first_key]:
           logging.warning(f"Values other: {first[first_key]['max']} and binrec: {second[first_key]} for {first_key} values are not the same")
       else:
           logging.info(f"Value {first[first_key]['max']} for {first_key} is the same!")

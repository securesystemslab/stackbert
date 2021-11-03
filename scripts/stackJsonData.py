import sys
import json

# sys.path.append("/home/chinmay/Projects/scratch/var/lib/python3.8/site-packages")
# import rzpipe

import pdb
import os
import binaryninja
import argparse

parser = argparse.ArgumentParser(description='Collect data for pin')
parser.add_argument('--file', metavar='F', 
        type=str, help='Input binary path')
parser.add_argument('--output', metavar='O', 
        type=str, help='Output file path')

args = parser.parse_args()

file_path = args.file
# file_name = file_path.split(os.sep)[-1]

if ".bndb" in file_path:
    sys.exit(1)

bndb_path = file_path + ".bndb"
# if os.path.exists(bndb_path):
#     print('[*] Using bndb')
#     bv = binaryninja.BinaryViewType.get_view_of_file(bndb_path)
# else:
bv = binaryninja.BinaryViewType.get_view_of_file(file_path)
if not bv:
    sys.exit(1)
bv.update_analysis_and_wait()
# bv.create_database(f"{bv.file.filename}.bndb", None, None)
# import pdb
# pdb.set_trace()

address_map = {}

def is_tail_exit(instr):
    if instr.operation in [binaryninja.LowLevelILOperation.LLIL_TAILCALL,
            binaryninja.LowLevelILOperation.LLIL_JUMP, 
            binaryninja.LowLevelILOperation.LLIL_CALL,
            binaryninja.LowLevelILOperation.LLIL_GOTO]:
        return 1
    else:
        # Can treat NORET as a normal call?
        # if instr.operation != binaryninja.LowLevelILOperation.LLIL_RET:
        #     print(instr.operation)
        return 0

print(f'[*] Analyzing {args.file}')
bbs_addresses = []
for function in bv.functions:
    if function is not None and function.analysis_skipped:
        function.analysis_skip_override = binaryninja.enums.FunctionAnalysisSkipOverride.NeverSkipFunctionAnalysis
        bv.update_analysis_and_wait()

    if function.symbol.type != binaryninja.SymbolType.FunctionSymbol:
        continue

    entry = function.start
    address_map[entry] = {}
    address_map[entry]['instrs'] = []
    for i in function.instructions:
        regs_written = function.get_regs_written_by(i[1])
        if "esp" in regs_written or "rsp" in regs_written:
            address_map[entry]['instrs'].append(i[1])
        address_map[entry]['name'] = function.name

    address_map[entry]['exits'] = {}
    for bb in function.llil:
        bbs_addresses.append(bb.source_block.start)
        
        if len(bb.outgoing_edges) != 0:
            continue

        instructions = [i for i in bb]
        last_instr = instructions[-1]
        address_map[entry]['exits'][last_instr.address] = is_tail_exit(last_instr)

with open(args.output, "w") as fp:
    for entry in address_map:
        if address_map[entry]['name'].startswith("_"):
            continue

        fp.write("0 " + str(entry) + "\n")
        for addr in address_map[entry]['instrs']:
            fp.write("1 " + str(addr) + "\n")
        for addr in address_map[entry]['exits']:
            fp.write("2 " + str(addr) + " " + str(address_map[entry]['exits'][addr]) + "\n")
        fp.write("3 " + address_map[entry]['name'] + "\n")

    for addr in bbs_addresses:
        fp.write("4 " + str(addr) + "\n")

# Rizin approach
# pipe = rzpipe.open(file_path)
# pipe.cmd("aa")
# address_map = {}
# def get_exit_addrs(func_name):
#     exit_addrs = []
#     fn_info = pipe.cmdj(f"afbj @ {func_name}")
#     for bb in fn_info:
#         if bb["outputs"] == 0:  # Check if outputs are 0
#             addr = bb["addr"]
#             bb_info = pipe.cmdj(f"pdbj @ {addr}")
#             exit_addrs.append(bb_info[-1]["offset"])
#     return exit_addrs
# with open(args.output, "w") as fp:
#     all_funcs = pipe.cmdj("aflj")
#     for func in all_funcs:
#         func_name = func['name']
#         if "sym." in func_name or func_name == "main":
#             if "sym.imp" in func_name or "sym._" in func_name:
#                 continue
#             fp.write("0 " + str(func["offset"]) + "\n")
#             exit_addrs = [int(x, 16) for x in pipe.cmd(f"afbr @ {func_name}").split("\n")[:-1]]
#             # exit_addrs = get_exit_addrs(func_name)
#             for exit_addr in exit_addrs:
#                 fp.write("1 " + str(exit_addr) + "\n")
#             all_instrs = pipe.cmdj(f"pdfj @ {func_name}")
#             for instr in all_instrs["ops"]:
#                 fp.write("2 " + str(instr["offset"]) + "\n")
#             fp.write("3 " + func_name + "\n")

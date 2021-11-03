#!/home/chinmay/Projects/scratch/var/bin/python

import sys
sys.path.append("/home/chinmay/Projects/scratch/var/lib/python3.8/site-packages")

import rzpipe
import gdb
import pdb

# TODO: Replace all instances of esp and eip with rsp and rip if target is 64 bits
gdb.execute("set pagination off")

fileName = gdb.current_progspace().filename
pipe = rzpipe.open(fileName)
pipe.cmd("aa")

address_map = {}
call_stack = []
first_entry = True

def get_reg_value(reg):
    # Maybe this way is faster
    return int(gdb.newest_frame().read_register(reg[1:]))
    # return int(gdb.parse_and_eval(reg))

class ESP_Watchpoint(gdb.Breakpoint):
    def stop(self):
        global call_stack

        if len(call_stack) == 0:
            return False

        eip_entry, esp_entry, func_name, max_diff = call_stack[-1]
        eip_value = get_reg_value("$eip")

        if eip_value not in address_map[eip_entry]["instrs"]:
            return False

        call_stack.pop()
        curr_esp = get_reg_value("$esp") 

        curr_diff = esp_entry - curr_esp
        max_diff = max(curr_diff, max_diff)

        call_stack.append((eip_entry, esp_entry, func_name, max_diff))

        return False

class Function_Entrypoint(gdb.Breakpoint):
    def stop(self):
        global call_stack, global_entry, address_map, first_entry

        if first_entry:
            ESP_Watchpoint("$esp", gdb.BP_WATCHPOINT, gdb.WP_WRITE)
            first_entry = False

        r_eip = get_reg_value("$eip")
        assert r_eip in address_map
        r_esp = get_reg_value("$esp")
        func_name = address_map[r_eip]["name"]

        # print(f"[+] {func_name}")

        call_stack.append((r_eip, r_esp, func_name, 0))
        global_entry = r_eip

        return False

class Function_Exitpoint(gdb.Breakpoint):
    def stop(self):
        global call_stack, global_entry, address_map

        r_eip = get_reg_value("$eip")
        eip_entry, final_esp, func_name, max_diff = call_stack.pop()

        # print(f"[-] {func_name}")
        
        address_map[eip_entry]["max"] = max(max_diff, address_map[eip_entry]["max"])
        if len(call_stack) != 0:
            global_entry, _, _, _ = call_stack[-1]

        return False

# Get a JSON of all functions from rizin
all_funcs = pipe.cmdj("aflj")
for func in all_funcs:
    func_name = func['name']
    # Ensure we dont track trampolines
    if ("sym." in func_name and "sym.imp." not in func_name) or func['name'] == "main":
        addr = func["offset"]
        address_map[addr] = {}
        address_map[addr]["name"] = func_name
        address_map[addr]["max"] = 0
        Function_Entrypoint(f"*{hex(addr)}", gdb.BP_BREAKPOINT)
        # Get all exit points for function from rizin
        exit_addrs = [int(x, 16) for x in pipe.cmd(f"afbr @ {func_name}").split("\n")[:-1]]
        address_map[addr]['exit_addrs'] = []
        for exit_addr in exit_addrs:
            address_map[addr]['exit_addrs'].append(exit_addr)
            Function_Exitpoint(f"*{hex(exit_addr)}", gdb.BP_BREAKPOINT)
        all_instrs = pipe.cmdj(f"pdfj @ {func_name}")
        address_map[addr]["instrs"] = {}
        for instr in all_instrs["ops"]:
            address_map[addr]["instrs"][instr["offset"]] = 1

print("================== BEGIN  RUN ===================")
gdb.execute("run")
print("================== END OF RUN ===================")

for addr in address_map:
    print(f"{address_map[addr]['name']} : {address_map[addr]['max']}")

gdb.execute("quit")


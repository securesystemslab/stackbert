# stacksyms.py: requires submodules pyelftools and dwarf_import.
# The purpose of this tool is to extract function features and labels
# for stack symbolization (total frame size, number and size of objects
# on stack) from unstripped, compiler-generated ELF files. While debug info
# isn't stricly required (only .eh_frame and .symtab are required) it certainly
# helps in generating better information. We obtain all information statically.
# Ideally, it can actually be validated at runtime (e.g, using GDB):
# (gdb) break {func.name}
# (gdb) r
# (gdb) rbreak .
# (gdb) c
# (gdb) info frame
# Now "frame at 0xA" - "called by frame at 0xB" should match our size estimate.

import os
import logging

from typing import Optional

# TODO: we really need unit tests..

# force local import of pyelftools
import sys; sys.path.insert(0, 'pyelftools')
import elftools
import elftools.dwarf, elftools.elf

from elftools.elf.elffile import ELFFile

from elftools.dwarf.descriptions import ExprDumper, describe_reg_name, \
     describe_CFI_register_rule, describe_CFI_CFA_rule

from dwarf_import.model.module import Module
from dwarf_import.model.elements import Component, Parameter, LocalVariable, \
     Location, Type, ScalarType, CompositeType, LocationType, ExprOp

from dwarf_import.io.dwarf_expr import ExprEval, LocExprParser
from dwarf_import.io.dwarf_import import DWARFDB, DWARFImporter
from dwarf_import.io.dwarf_import import place_component_in_module_tree

# Vector35's dwarf_import library has:
#   (1) the io classes which deal with ELF/DWARF stuff,
#   (2) the model classes which are more general, high-level data containers
#   (3) the parsers themselves (stateful because DWARF contains stack machines)
# Some things (like lineprograms) are not implemented in any library I looked at.
#
# Their DWARF EH_FRAME processing most likely comes from this repo:
# https://github.com/francesco-zappa-nardelli/eh_frame_check/blob/master/testing/eh_frame_check.py
# there are some interesting test cases here:
# https://git.tobast.fr/m2-internship/eh_frame_check_setup
import dwarf_import

logging.basicConfig(
#    filename='stacksyms_run.log',
    format='{asctime} {levelname}:{funcName}:{message}',
    style="{", datefmt='%m/%d/%Y %H:%M:%S', level=logging.CRITICAL,
)

class Register(dwarf_import.model.elements.Element):
    '''Dataclass for spilled registers'''
    type = Type(name='Register')
    def __init__(self, number, name, locations):
        super().__init__(owner=None, name=name)
        self.locations = locations # iterable (e.g., set)
        self.number = number # int or str
    def __repr__(self):
        return f'<Register: number={self.number}, name={self.name}, ' \
                        + f'locations={self.locations}>'

class Function(dwarf_import.model.elements.Function):
    '''Dataclass for parsed symbol definitions (including opcodes).'''
    @classmethod
    def fromDWARFFunction(cls, old: dwarf_import.model.elements.Function):
        new = cls(owner=old.owner, name=old.name, start=old.start)
        new._return_type = old._return_type
        new._access = old._access
        new._no_return = old._no_return
        for p in old._parameters:
            new.add_parameter(p.clone())
        for v in old._variables:
            new.add_variable(v.clone())
        if hasattr(old, '_attributes'):
            new._attributes = dict(old._attributes)
        return new
    
    def __init__(self, owner = None, name: str = 'function', \
                 start: Optional[int] = None):
        super().__init__(owner, name, start)
        self._is_inline = False
        self._arch = '' # arch string (e.g., 'arm', 'AArch64', 'x86', 'x64')
        self._size = 0  # size of function code in bytes
        self._frame_table = None # FDE or None
        self._registers = dict() # maps register names to locations
        self._code = None # opcode string as bytes object

    @property
    def is_inline(self) -> bool:
        return self._is_inline

    @property
    def arch(self) -> str:
        return self._arch

    @property
    def size(self) -> int:
        return self._size

    @property
    def frame_table(self) -> elftools.dwarf.callframe.FDE:
        return self._frame_table

    @property
    def registers(self) -> list:
        return list(self._registers.values())

    @property
    def code(self) -> str:
        if self._code is not None:
            return self._code.hex()
        return ''

# This is the entry point (use together with 'predictStackFrameLayout').
def parseELF(filepath):
    '''Returns a list of functions (if the file contains frame info section)'''
    logging.info(f"Trying to parse {filepath} as ELF")
    elf = ELFFile(open(filepath, 'rb'))
    logging.info(f"ELF file is for architecture {elf.get_machine_arch()}.")
    module, importer = parseDWARF(elf)
    # a map of int (pc values) -> model.elements.Function
    func_dict = getAllFunctions(module, importer, elf)
    # int (pc values) -> FDE dict
    frame_tables = collectFrameInfo(func_dict, elf)
    func_dict = assign_frames(frame_tables, func_dict) # split per function
    # process dynamic register locs
    func_dict = processRegisterRuleExpressions(func_dict, importer)
    # element.type.byte_size is often None -> try and fix it
    func_dict = propagateTypeInfo(func_dict, importer)
    func_dict = collectOpcodes(func_dict, elf) # read bytes from .text section
    processInlineFunctions(func_dict, importer, elf)
    return func_dict.values()

# This is the main interface for obtaining predictions (pass result of 'parseELF').
def predictStackframeLayouts(functions, want_analysis=False):
    '''Returns a list of function frame layout predictions. Requires capstone
       installation if want_analysis=True (generally improves results).'''
    logging.info(f"Collecting predictions for {len(functions)} functions.")
    allLabels = {}
    for func in functions:
        if not func.is_inline:
            funclabel = dict()
            funclabel['inp'] = ' '.join([
                func.code[i:i+2] for i in range(0, len(func.code), 2)
            ])
            funclabel['max'] = getMaxFrameSize(func)
            funclabel['out'] = generateDebugLabel(func)
            funclabel['maxCFA'] = getMaxFrameSizeCFA(func)
            if want_analysis: # requires capstone
                stackops, maxstack  = disassembleAndAnalyzeSymbolically(func)
                funclabel['maxANA'] = maxstack
                funclabel['outANA'] = stackops
                logging.info(f"{func.name} ({funclabel['max']}" \
                            +f"/ {sum(funclabel['out'])} " \
                            +f"/ {funclabel['maxCFA']} " \
                            +f"/ {funclabel['maxANA']}) " \
                            +f"=> {funclabel['out']} / {funclabel['outANA']}")
            else:
                logging.info(f"{func.name} ({funclabel['max']}" \
                            +f"/ {sum(funclabel['out'])} " \
                            +f"/ {funclabel['maxCFA']} " \
                            +f"=> {funclabel['out']}")
            allLabels[func.name] = funclabel
    return allLabels

# TODO: if frame table is indeed missing, try generating it
# e.g., using https://github.com/frdwarf/dwarf-synthesis
def parseDWARF(elf):
    '''Parse .eh_frame section (if present - strip retains frame info)'''
    if elf.has_dwarf_info(): # note that this does NOT mean 'has_debug_info()'
        logging.info("ELF file says it has some frame info..")
        module = Module()
        dwarfDB = DWARFDB(elf) # io data class for parsing
        # passing {'only_concrete_subprograms' : False} yields start=0 symbols
        importer = DWARFImporter(dwarfDB, dict())
        for component in importer.import_components():
            place_component_in_module_tree(module, component)
        return module, importer # importer has state after parsing
    raise RuntimeError("ELF file does not contain required information!")

# TODO: relies on .symtab or .dynsym -> support external symbol discovery
def getAllFunctions(module, importer, elf):
    '''Returns dwarf_import.model.elements.Function objects.'''
    # from the .symtab section (name, address, and size only)
    func_dict = getFunctionsFromSymtab(elf)
    # TODO: from .eh_frame (no names but frame size and address ranges)
    # from .debug_info using 'DW_TAG_subprogram'
    func_dict = getFunctionsFromDWARFInfo(func_dict, module)
    return func_dict

# process inline functions to obtain frame information for parent functions
def processInlineFunctions(func_dict, importer, elf):
    inlinedFs = {
        func.start : func \
        for func in getInlined(func_dict.values()) \
        if func.start not in func_dict \
    }
    if len(inlinedFs) == 0:
        return
    logging.debug(f"Found {len(inlinedFs)} inlined functions.")
    sorted_funcs = sorted(func_dict.values(), key=lambda f : f.start)
    for func in inlinedFs.values():
        func._is_inline = True
        func._arch = elf.get_machine_arch()
        parent = binary_search_function(func.start, sorted_funcs)
        if parent is None:
            logging.warn(f"Inlined function without parent: {func}")
            continue
        if func not in parent.inlined_functions:
            if parent._inlined_functions == None:
                parent._inlined_functions = (func,)
            else:
                parent._inlined_functions += (func,)
    inlined_frame_tables = collectFrameInfo(inlinedFs, elf)
    inlinedFs = assign_frames(inlined_frame_tables, inlinedFs)
    inlinedFs = processRegisterRuleExpressions(inlinedFs, importer)
    inlinedFs = propagateTypeInfo(inlinedFs, importer)
    return

# TODO: for some reason, there may be duplicates?
def getInlined(functions):
    '''Recursively finds all inlined functions'''
    level=[inlined for func in functions for inlined in func.inlined_functions]
    if not any(level):
        return functions
    return level + getInlined(level)

def getFunctionsFromSymtab(elf):
    '''Get both local and global symbols from .symtab section.'''
    logging.info('Trying to obtain symbol information.')
    Register.type._byte_size = getRegisterSize(elf.get_machine_arch())
    func_dict = dict()
    symtab = elf.get_section_by_name('.symtab')
    if symtab is None:
        logging.warning("Missing .symtab section, trying .dynsym..")
        symtab = elf.get_section_by_name('.dynsym')
        if symtab is None:
            logging.critical("Missing .symtab and .dynsym sections, " \
                             + "cannot obtain symbol information!")
            return func_dict
    for i, symbol in enumerate(symtab.iter_symbols()):
        if symbol['st_info']['type']=='STT_FUNC':
            if symbol['st_value']==0:
                # for dynamic symbols 'st_value' and 'st_size' will be zero
                logging.warn(f"Undefined symbol {symbol.name} (dynamic?)")
                # FIXME: could add support for shared libraries
                # -> probably not a good idea for a "static" tool though
            elif symbol['st_value'] not in func_dict:
                new_func = Function(name=symbol.name, start=symbol['st_value'])
                new_func._arch = elf.get_machine_arch()
                new_func._size = symbol['st_size']
                func_dict[symbol['st_value']] = new_func
    logging.info(f'Found {len(func_dict)} functions according to symbol table')
    return func_dict

def getFunctionsFromDWARFInfo(func_dict, module):
    '''Recursively finds functions using 'DW_TAG_subprogram'.'''
    logging.info(f'Searching for subroutines with explicit DWARF info..')
    for m in module.children():
        if isinstance(m, Module):
            logging.debug(f'Recursing into module {m}')
            getFunctionsFromDWARFInfo(func_dict, m)
        elif isinstance(m, Component):
            logging.debug(f'{len(m.functions)} functions in component {m.name}')
            func_dict = mergeSymtabDWARF(func_dict, m.functions)
        else:
            logging.critical(f'Neither Module nor Component ({type(m), m}).')
    return func_dict

def mergeSymtabDWARF(symtab_funcs, dwarf_funcs):
    for dwarf_func in dwarf_funcs:
        if dwarf_func.start is None: # try to match it by name
            for symtab_func in symtab_funcs.values():
                if symtab_func.name == dwarf_func.name:
                    logging.info(f'Found missing address from symtab' \
                                 + f'for {dwarf_func.name}.')
                    dwarf_func.start = symtab_func.start
                    break
            else: # this case only hits if we did not break the inner loop
                logging.info(f'Skipping abstract function ' \
                             + f'{dwarf_func.name} (missing address).')
                continue # skip outer loop (no matching function)
        # try merging symtab and DWARF symbols by address
        if dwarf_func.start in symtab_funcs:
            logging.debug(f'Merging symtab and dwarf info for ' \
                          + '{dwarf_func.name}@{hex(dwarf_func.start)}.')
            symtab_func = symtab_funcs[dwarf_func.start]
            new_func = Function.fromDWARFFunction(dwarf_func)
            new_func._size  = symtab_func.size
            new_func._arch  = symtab_func.arch
            symtab_funcs[new_func.start] = new_func
            del symtab_func
    return symtab_funcs

def collectFrameInfo(func_dict, elf):
    '''Parses .eh_frames to collect frame tables per function
       (specified in DWARF Standard Section 6.4.1)'''
    from elftools.dwarf.callframe import CIE, FDE, ZERO
    dwarfInfo = elf.get_dwarf_info()
    if dwarfInfo.has_EH_CFI(): # ez
        logging.info('has .eh_frames')
        cfi_entries = dwarfInfo.EH_CFI_entries()
        frame_tables = dict() # func.start -> frame description entry (FDE)
        for entry in cfi_entries: # FDEs or CIEs
            if isinstance(entry, FDE): # CIEs don't specify location (FDEs do)
                fpc = entry['initial_location']
                func = func_dict[fpc] if fpc in func_dict else None
                if func is None:
                    logging.warn("FDE/CIE for address " \
                                 + f"{hex(entry['initial_location'])} " \
                                 + "without matching symbol.")
                    continue
                frame_tables[func.start] = entry
        return frame_tables # TODO: handle .debug_frames
    logging.critical('File does not contain .eh_frames section')
    return func_dict

def binary_search_function(address, sorted_functions):
    '''Finds the function among the provided list that best matches the provided
       address (assuming linearly sorted func.start values and a contiguous code
       region).'''
    left = 0
    right = len(sorted_functions)-1
    while left <= right:
        mid = (left + right) // 2
        if sorted_functions[mid].start < address:
            left = mid + 1
        elif address < sorted_functions[mid].start:
            right = mid - 1
        else:
            return sorted_functions[mid]
    if sorted_functions[right].start <= address:
        return sorted_functions[right]
    elif sorted_functions[left].start <= address:
        return sorted_functions[left]
    return None

def assign_frames(frame_tables, func_dict):
    '''Assign FDEs to functions by address matching fde['pc'] with func.start'''
    for func in func_dict.values():
        func._frame_table = None
        if func.start not in frame_tables:
            if not func.is_inline:
                logging.critical(f"No frame table for " \
                               + f"{func.name}@{hex(func.start)}!")
            continue
        entry = frame_tables[func.start] # FDE
        decoded_table = entry.get_decoded() # DecodedCallFrameTable
        if len(decoded_table) == 0:
            logging.warn(f'Frame table for function {func.name} is empty!')
            continue
        func._frame_table = entry
    return func_dict

def processRegisterRuleExpressions(func_dict, importer):
    '''Process frame tables to create locations for registers on the stack'''
    # TODO this is a hack, should be part of the dwar_import processing..
    # TODO missing inlined functions without their own frame table (some do)
    for func in func_dict.values():
        if func.frame_table is not None:
            decoded_table = func.frame_table.get_decoded()
            ra_regnum = func.frame_table.cie['return_address_register']
            gp = [r for r in decoded_table.reg_order if r != ra_regnum]
            for line in func.frame_table.get_decoded().table:
                if 'cfa' in line: # canonical frame address rule
                    processCFARule(line, func, importer)
                for reg in sorted(gp): # general purpose register rules
                    if reg in line:
                        processRegisterRule(reg, line, func, importer)
    return func_dict

def processCFARule(line, func, importer):
    pc = line['pc'] # start address for rules in this line
    cfa_loc = None
    if line['cfa'].expr:
        cfa_loc=importer._location_factory.make_location(pc,0,line['cfa'].expr)
    else:  # tuple (0, ) unifies access to [1] in all cases later
        cfa_loc=Location(pc,0,LocationType.STATIC_LOCAL,(0,line['cfa'].offset))
    if 'cfa' not in func._registers:
        regname = describe_reg_name(line['cfa'].reg, func.arch)
        func._registers['cfa'] = Register('cfa', regname, set())
    if cfa_loc is not None:
        func._registers['cfa'].locations.update({cfa_loc})
    else:
        logging.critical(f"{describe_CFI_CFA_rule(line['cfa'])}@{func.name}.")
    return

def processRegisterRule(regNo, line, func, importer):
    pc = line['pc'] # start address for rules in this line
    loc = None
    if line[regNo].type in ['OFFSET', 'VAL_OFFSET']:
        loc = Location(pc, 0, LocationType.STATIC_LOCAL, (0, line[regNo].arg))
    elif line[regNo].type in ['EXPRESSION', 'VAL_EXPRESSION']:
        loc = importer._location_factory.make_location(pc, 0, line[regNo].arg)
        if loc is None:
            logging.critical(f"Location was 'None' for regrule in {func.name}:")
            logging.critical(f"{describe_CFI_register_rule(line[regNo])}.")
            return
    else: # no stack location
        return
    if regNo not in func._registers:
        regname = describe_reg_name(regNo, func.arch)
        func._registers[regNo] = Register(regNo, regname, set())
    func._registers[regNo].locations.update({loc})
    return

def getRegisterSize(arch):
    return {
        'x86'     : 4,
        'x64'     : 8,
        'ARM'     : 4,
        'AArch64' : 8,
    }[arch]

# TODO There seem to be two remaining 'None' type sources: VOID and VARIADIC.
#      Not sure if there is a general way of dealing with them correctly,
#      so we don't provide any size information for them at the moment.
def propagateTypeInfo(func_dict, importer):
    types = set() #for Type in importer._type_factory.iter_types():
    arch = None
    for function in func_dict.values():
        arch = function.arch
        for parameter in function.parameters:
            if parameter.type is None:
                logging.warn(f"Parameter {parameter} has 'None' type.")
                continue
            types |= {parameter.type}
        for variable in function.variables:
            if variable.type is None:
                logging.warn(f"Variable {variable} has 'None' type.")
                continue
            types |= {variable.type}
    logging.debug(f"Type list for functions: {types}.")
    for _type in types: # we want to process most types (even with byte size)
        if not _type.is_qualified_type or _type.byte_size is None:
            if _type.array_count is not None: # arrays
                if _type.element._scalar_type==ScalarType.POINTER_TYPE:
                    if _type.byte_size is None: # data pointers
                        _type._byte_size = _type.array_count \
                            * getRegisterSize(arch)
                        continue
                elif resolveType(_type, True)._scalar_type \
                     == ScalarType.POINTER_TYPE: # code pointers
                    if _type.byte_size is None:
                        _size = _type.array_count * getRegisterSize(arch)
                        _type._byte_size = _size
                        continue
                elif _type.byte_size is None: # non-pointer arrays
                    arrayType = resolveType(_type)
                    if arrayType.byte_size is not None:
                        _size = _type.array_count * arrayType.byte_size
                        _type._byte_size = _size
                        continue
                logging.critical(f"Cannot resolve array type {_type}")
            elif _type.composite_type is not None: # FIXME implement this
                if _type.byte_size is None: 
                    logging.critical(f"Can't yet handle type {_type} with " \
                                   + f"composite {_type.composite_type}!")
            elif _type.element is not None: # this is the frequent case
                base = resolveType(_type)
                if base.byte_size is None:
                    logging.warn(f"Resolving type {base} yields size 'None'!")
                    continue
                _type._byte_size = base._byte_size
    return func_dict

def resolveType(_type, secondToLast=False):
    if secondToLast: # find function pointer arrays (e.g., 'void()*[100]')
        if _type.element is not None and _type.element.element is not None:
            if _type.element.element.element is None:
                if _type.element._composite_type == CompositeType.FUNCTION_TYPE:
                    return _type
                return _type.element
            return resolveType(_type.element, secondToLast)
    return _type if _type.element is None else resolveType(_type.element)

def getMaxFrameSize(func):
    inlined = [getStackElements(inlined) for inlined in func.inlined_functions]
    logging.debug(f"Got {len(inlined)} inlined stack slots for {func.name}")
    stack = func.parameters + func.variables + func.registers + inlined
    locations = [0]+[
        loc.expr[1] for stkElm in stack for loc in getStackLocations(stkElm)
    ]
    return max(map(abs, locations))

def getMaxFrameSizeCFA(function):
    cfaLocExprs = [0]
    if 'cfa' in function._registers:
        for loc in getStackLocations(function._registers['cfa']):
            cfaLocExprs += [loc.expr[1]]
    return max(cfaLocExprs)

def getStackElements(function):
    '''return stack elements (in no particular order)'''
    candidates = function.parameters + function.variables + function.registers
    return [stkElm for stkElm in candidates if any(getStackLocations(stkElm))]

# stkElm can be Register, LocalVariable, or Parameter
def getStackLocations(stkElm):
    return [loc for loc in stkElm.locations if locExprHasOffset(loc)]

def locExprHasOffset(location): # TODO y0 d4wg, this sh!t is sketchy as f*&^
    if location.type in [LocationType.STATIC_GLOBAL, LocationType.STATIC_LOCAL, LocationType.DYNAMIC]:
        return len(location.expr) > 1 and type(location.expr[1]) == int
    return False

# inspired by 'readelf -x'
def collectOpcodes(func_dict, elf):
    '''pyelftools standalone opcode retrieval (should be fast)'''
    from elftools.elf.constants import SH_FLAGS
    code_sections = {}
    for section in elf.iter_sections():
        if section['sh_flags'] & SH_FLAGS.SHF_EXECINSTR:
            start = section['sh_addr']
            end   = start + section['sh_size']
            if start < end:
                code_sections[(start, end)] = section
    if len(code_sections) == 0:
        logging.critical("File has no executable sections!")
        return func_dict
    for func in func_dict.values():
        if func.is_inline:
            continue
        for section_start, section_end in code_sections.keys():
            if section_start <= func.start <= section_end:
                section = code_sections[(section_start, section_end)]
                if func.start%section['sh_addralign'] != 0:
                    logging.debug(f"Function {func.name}@{hex(func.start)} does not adhere to section alignment.")
                start_off = func.start - section_start
                end_off   = func.start + func.size - section_start
                func._code = section.data()[start_off:end_off+1]
                break
        if func.code is None:
            logging.critical(f"Symbol {func.name}@{hex(func.start)} undefined, opcodes missing!")
    return func_dict

def generateDebugLabel(func):
    funElms  = len(func.parameters) + len(func.variables) + len(func.registers)
    inlinedStackElms = [getStackElements(inlined) for inlined in func.inlined_functions]
    stkSlots = sorted(getStackElements(func) + inlinedStackElms, key=getMaxStackOff)
    if len(stkSlots) != funElms:
        logging.info(f"Function {func.name} has {len(stkSlots)} stack elements out of {funElms} total.")
    logging.debug(f"{func.name} => [{', '.join(stkElm.name+'@ebp%+d'%getMaxStackOff(stkElm) for stkElm in stkSlots)}]")
    stack = [
        stkElm.type.byte_size if stkElm.type.byte_size is not None
        else 0 # e.g., if type propagation failed for that slot
        for stkElm in stkSlots
    ]
    return stack # NoneTypes slots are 0

def getMaxStackOff(stkElm): # maximal stack offset for a single element
    stkLocs = getStackLocations(stkElm)
    logging.debug(f"Stack element {stkElm} has {len(stkLocs)} stack locations.")
    return max(map(lambda stkLoc : abs(stkLoc.expr[1]), stkLocs))

# We do a single linear sweep. While this is fast, it may be inaccurate.
# One could in principle use a symbolic execution engine (e.g. angr),
# however, in general more complex analyses may not even converge.
def disassembleAndAnalyzeSymbolically(func):
    if func.arch == 'x64':
        return disasAndAnalyzeStackAMD64(func)
    elif func.arch == 'AArch64':
        return disasAndAnalyzeStackAArch64(func)
    elif func.arch == 'x86':
        return disasAndAnalyzeStackAMD64(func, m32=True)
    raise RuntimeError(f"Architecture {func.arch} is not supported yet!")

def disasAndAnalyzeStackAMD64(func, m32=False):
    import re; import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32 if m32 else capstone.CS_MODE_64)
    non_hexdigits = re.compile(r'[^\dx]+')
    md.detail = True
    regsize = getRegisterSize(func.arch)
    maxstack = 0
    stackops = []
    for i in md.disasm(bytes.fromhex(func.code), func.start):
        if i.mnemonic == 'push':
            stackops += [regsize]
        elif i.mnemonic == 'pop':
            stackops += [-regsize]
        elif 'sp' in i.op_str:
            regs_read, regs_write = i.regs_access()
            if 0 < len(regs_write) and 'sp' in [i.reg_name(r) for r in regs_write]:
                if i.mnemonic == 'sub':
                    stackops += [int(i.op_str.split(' ')[1], 16)]
                elif i.mnemonic == 'add':
                    stackops += [-int(i.op_str.split(' ')[1], 16)]
                elif i.mnemonic == 'mov':
                    pass # FIXME I guess we can't do much here?
                else:
                    raise RuntimeError(f"0x{hex(i.address)}:\t{i.mnemonic}\t{i.op_str}")
        _sum  = sum(stackops)
        maxstack = _sum if maxstack < _sum else maxstack
    return stackops, maxstack

def disasAndAnalyzeStackAArch64(func):
    import re; import capstone
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    md.detail = True
    non_hexdigits = re.compile(r'[^\dx]+')
    maxstack = 0
    stackops = []
    for i in md.disasm(bytes.fromhex(func.code), func.start):
        if 'sp' in i.op_str:
            regs_read, regs_write = i.regs_access()
            if 0 < len(regs_write) and 'sp' in [i.reg_name(r) for r in regs_write]:
                split = i.op_str.split(' ')
                if i.mnemonic == 'stp':
                    stackops += [int(non_hexdigits.sub('', split[3]), 16)]
                elif i.mnemonic == 'ldp':
                    stackops += [-int(non_hexdigits.sub('', split[3]), 16)]
                elif i.mnemonic in ['sub', 'str']:
                    stackops += [int(non_hexdigits.sub('', split[2]), 16)]
                elif i.mnemonic in ['add', 'ldr']:
                    stackops += [-int(non_hexdigits.sub('', split[2]), 16)]
                else:
                    raise RuntimeError(f"0x{hex(i.address)}:\t{i.mnemonic}\t{i.op_str}")
        _sum  = sum(stackops)
        maxstack = _sum if maxstack < _sum else maxstack
    return stackops, maxstack

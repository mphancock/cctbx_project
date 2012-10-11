
from __future__ import division
from libtbx.utils import Sorry, Usage, null_out
import libtbx.phil
import os
import sys

sorting_params_str = """
waters_only = False
  .type = bool
  .help = Rearrange waters, but leave all other ligands alone.
sort_waters_by = none *b_iso
  .type = choice
  .help = Ordering of waters - by default it will sort them by the isotropic \
    B-factor.
set_hetatm_record = True
  .type = bool
  .help = Convert ATOM to HETATM where appropriate.
ignore_selection = None
  .type = atom_selection
  .help = Selection of atoms to skip.  Any residue group which overlaps with \
    this selection will be preserved with the original chain ID and numbering.
renumber = True
  .type = bool
  .help = Renumber heteroatoms once they are in new chains.
sequential_numbering = True
  .type = bool
  .help = If True, the heteroatoms will be renumbered starting from the next \
    available residue number after the end of the associated macromolecule \
    chain.  Otherwise, numbering will start from 1.
distance_cutoff = 6.0
  .type = float
  .help = Cutoff for identifying nearby macromolecule chains.  This should be \
    kept relatively small for speed reasons, but it may miss waters that are \
    far out in solvent channels.
loose_chain_id = X
  .type = str
  .help = Chain ID assigned to heteroatoms that can't be mapped to a nearby \
    macromolecule chain.
"""

master_phil = """
file_name = None
  .type = path
output_file = None
  .type = path
unit_cell = None
  .type = unit_cell
space_group = None
  .type = space_group
ignore_symmetry = False
  .type = bool
preserve_remarks = True
  .type = bool
verbose = False
  .type = bool
%s
""" % sorting_params_str

def sort_hetatms (
    pdb_hierarchy,
    xray_structure,
    params=None,
    verbose=False,
    log=null_out()) :
  """
  Rearrange a PDB hierarchy so that heteroatoms are grouped with the closest
  macromolecule, accounting for symmetry.  Assorted ligands will be arranged
  first in each new chain, followed by waters.  See the PHIL block
  sorting_params_str for options.
  """
  if (params is None) :
    import iotbx.phil
    params = iotbx.phil.parse(sorting_params_str).fetch().extract()
  from iotbx import pdb
  from scitbx.array_family import flex
  pdb_atoms = pdb_hierarchy.atoms()
  pdb_atoms.reset_i_seq()
  # the i_seq will be reset in various places, so I substitute the tmp
  # attribute
  for atom in pdb_atoms :
    atom.tmp = atom.i_seq # XXX why can't this be an array operation?
  pdb_atoms = pdb_hierarchy.deep_copy().atoms()
  n_atoms = pdb_atoms.size()
  assert (n_atoms == len(xray_structure.scatterers()))
  ignore_selection = flex.bool(n_atoms, False)
  mm_selection = flex.bool(n_atoms, False)
  sites_frac = xray_structure.sites_frac()
  new_sites_cart = xray_structure.sites_cart()
  pair_asu_table = xray_structure.pair_asu_table(
    distance_cutoff=params.distance_cutoff)
  asu_mappings = pair_asu_table.asu_mappings()
  asu_table = pair_asu_table.table()
  mm_chains = []
  hetatm_chains = []
  if (params.ignore_selection is not None) :
    sel_cache = pdb_hierarchy.atom_selection_cache()
    ignore_selection = sel_cache.selection(params.ignore_selection)
  assert (len(pdb_hierarchy.models()) == 1)
  for chain in pdb_hierarchy.only_model().chains() :
    main_conf = chain.conformers()[0]
    if (main_conf.is_protein()) or (main_conf.is_na()) :
      mm_chains.append(chain)
      i_seqs = chain.atoms().extract_tmp_as_size_t()
      mm_selection.set_selected(i_seqs, True)
    else :
      hetatm_chains.append(chain)
  if (len(hetatm_chains) == 0) :
    print >> log, "No heteroatoms - hierarchy will not be modified."
    return pdb_hierarchy
  new_hierarchy = pdb.hierarchy.root()
  new_model = pdb.hierarchy.model()
  new_chain_i_seqs = []
  new_hierarchy.append_model(new_model)
  new_hetatm_chains = []
  new_start_resseq = []
  for chain in mm_chains :
    new_chain_i_seqs.append(flex.size_t(chain.atoms().extract_tmp_as_size_t()))
    new_model.append_chain(chain.detached_copy())
    new_hetatm_chains.append(pdb.hierarchy.chain(id=chain.id))
    if (params.sequential_numbering) :
      last_resseq = chain.residue_groups()[-1].resseq_as_int()
      new_start_resseq.append(last_resseq + 1)
    else :
      new_start_resseq.append(1)
  hetatm_residue_groups = []
  loose_residues = pdb.hierarchy.chain(id=params.loose_chain_id)
  preserve_chains = []
  for chain in hetatm_chains :
    for rg in chain.residue_groups() :
      keep_residue_group = False
      rg_atoms = rg.atoms()
      i_seqs = rg_atoms.extract_tmp_as_size_t()
      atom_groups = rg.atom_groups()
      if ((params.waters_only) and
          (not atom_groups[0].resname in ["HOH","WAT"])) :
        keep_residue_group = True
      else :
        for i_seq in i_seqs :
          if (ignore_selection[i_seq]) :
            keep_residue_group = True
            break
      if (not keep_residue_group) :
        rg_copy = rg.detached_copy()
        for new_atom, old_atom in zip(rg_copy.atoms(), rg_atoms) :
          new_atom.tmp = old_atom.tmp # detached_copy() doesn't preserve tmp
        hetatm_residue_groups.append(rg_copy)
        chain.remove_residue_group(rg)
    if (len(chain.residue_groups()) > 0) :
      preserve_chains.append(chain.detached_copy())
  for chain in preserve_chains :
    new_model.append_chain(chain)
  unit_cell = xray_structure.unit_cell()
  for rg in hetatm_residue_groups :
    rg_atoms = rg.atoms()
    i_seqs = rg_atoms.extract_tmp_as_size_t()
    closest_distance = sys.maxint
    closest_i_seq = None
    closest_rt_mx = None
    for i_seq, atom in zip(i_seqs, rg_atoms) :
      if (params.set_hetatm_record) :
        atom.hetero = True
      site_i = sites_frac[i_seq]
      asu_dict = asu_table[i_seq]
      rt_mx_i_inv = asu_mappings.get_rt_mx(i_seq, 0).inverse()
      for j_seq, j_sym_groups in asu_dict.items() :
        if (not mm_selection[j_seq]) :
          continue
        site_j = sites_frac[j_seq]
        for j_sym_group in j_sym_groups:
          rt_mx = rt_mx_i_inv.multiply(asu_mappings.get_rt_mx(j_seq,
            j_sym_group[0]))
          site_ji = rt_mx * site_j
          dxyz = unit_cell.distance(site_i, site_ji)
          if (dxyz < closest_distance) :
            closest_distance = dxyz
            closest_rt_mx = rt_mx.inverse() # XXX I hope this is right...
            closest_i_seq = j_seq
    if (closest_i_seq is None) :
      print >> log, "Residue group %s is not near any macromolecule chain" % \
        rg.id_str()
      loose_residues.append_residue_group(rg)
    else :
      for j_seqs, hetatm_chain in zip(new_chain_i_seqs, new_hetatm_chains) :
        if (closest_i_seq in j_seqs) :
          if (verbose) :
            if (closest_rt_mx.is_unit_mx()) :
              print >> log, \
                "Residue group %s added to chain %s (distance = %.3f)" % \
                (rg.atoms()[0].id_str(), hetatm_chain.id, closest_distance)
            else :
              print >> log, \
                ("Residue group %s added to chain %s "+
                 "(distance = %.3f, symop = %s)") % \
                (rg.atoms()[0].id_str(), hetatm_chain.id, closest_distance,
                 str(closest_rt_mx))
          if (not closest_rt_mx.is_unit_mx()) :
            # closest macromolecule is in another ASU, so map the hetatms to
            # be near the copy in the current ASU
            for atom in rg.atoms() :
              site_frac = unit_cell.fractionalize(site_cart=atom.xyz)
              new_site_frac = closest_rt_mx * site_frac
              atom.xyz = unit_cell.orthogonalize(site_frac=new_site_frac)
          hetatm_chain.append_residue_group(rg)
          break
      else :
        raise RuntimeError("Can't find chain for i_seq=%d" % closest_i_seq)
  # even if waters aren't sorted, we still want them to come last
  for chain in new_hetatm_chains :
    waters_and_b_iso = []
    for rg in chain.residue_groups() :
      ags = rg.atom_groups()
      if (ags[0].resname in ["WAT","HOH"]) :
        b_iso = flex.mean(rg.atoms().extract_b())
        waters_and_b_iso.append((rg, b_iso))
        chain.remove_residue_group(rg)
    if (len(waters_and_b_iso) > 0) :
      if (params.sort_waters_by != "none") :
        waters_and_b_iso.sort(lambda x,y: cmp(x[1], y[1]))
      for water, b_iso in waters_and_b_iso :
        chain.append_residue_group(water)
  if (params.renumber) :
    for chain, start_resseq in zip(new_hetatm_chains, new_start_resseq) :
      resseq = start_resseq
      for rg in chain.residue_groups() :
        rg.resseq = resseq
        resseq += 1
  for chain in new_hetatm_chains :
    for residue_group in chain.residue_groups() :
      residue_group.link_to_previous = True # suppress BREAK records
    new_model.append_chain(chain)
  if (len(loose_residues.residue_groups()) > 0) :
    new_model.append_chain(loose_residues)
  n_atoms_new = len(new_hierarchy.atoms())
  if (n_atoms_new != n_atoms) :
    raise RuntimeError("Atom counts do not match: %d --> %d" % (n_atoms,
      n_atoms_new))
  return new_hierarchy

def run (args, out=sys.stdout) :
  import iotbx.phil
  if (len(args) == 0) or ("--help" in args) :
    raise Usage("""\
mmtbx.sort_hetatms model.pdb [options]

Rearrange non-macromolecular heteroatoms (waters and other ligands, by default)
into new chains having the same ID as the closest macromolecule chain.  Will
also renumber residues and sort waters by B-factor with default settings.

Full parameters:

%s
""" % iotbx.phil.parse(master_phil).as_str(prefix="  "))
  from iotbx import file_reader
  from cctbx import crystal
  cmdline = iotbx.phil.process_command_line_with_files(
    args=args,
    master_phil_string=master_phil,
    pdb_file_def="file_name")
  params = cmdline.work.extract()
  validate_params(params)
  pdb_in = file_reader.any_file(params.file_name, force_type="pdb")
  pdb_in.check_file_type("pdb")
  pdb_symm = pdb_in.file_object.crystal_symmetry()
  space_group = params.space_group
  unit_cell = params.unit_cell
  if (pdb_symm is None) and (not params.ignore_symmetry) :
    if (space_group is None) or (unit_cell is None) :
      raise Sorry("Crystal symmetry information is required; please specify "+
        "the space_group and unit_cell parameters.")
  else :
    if (space_group is None) :
      space_group = pdb_symm.space_group_info()
    if (unit_cell is None) :
      unit_cell = pdb_symm.unit_cell()
  final_symm = None
  if (not params.ignore_symmetry) :
    final_symm = crystal.symmetry(
      space_group_info=space_group,
      unit_cell=unit_cell)
  pdb_hierarchy = pdb_in.file_object.construct_hierarchy()
  pdb_hierarchy.atoms().reset_i_seq()
  xray_structure = pdb_in.file_object.xray_structure_simple(
    crystal_symmetry=final_symm,
    unit_cube_pseudo_crystal=params.ignore_symmetry)
  new_hierarchy = sort_hetatms(
    pdb_hierarchy=pdb_hierarchy,
    xray_structure=xray_structure,
    params=params,
    verbose=params.verbose,
    log=out)
  if (params.output_file is None) :
    params.output_file = os.path.splitext(
      os.path.basename(params.file_name))[0] + "_sorted.pdb"
  f = open(params.output_file, "w")
  if (params.preserve_remarks) :
    f.write("\n".join(pdb_in.file_object.remark_section()))
    f.write("\n")
  f.write(new_hierarchy.as_pdb_string(crystal_symmetry=final_symm))
  f.close()
  print >> out, "Wrote %s" % params.output_file
  return os.path.basename(params.output_file)

def validate_params (params) :
  if (params.file_name is None) :
    raise Sorry("PDB file (file_name) not specified.")
  return True

if (__name__ == "__main__") :
  run(sys.argv[1:])

from __future__ import absolute_import, division, print_function
import iotbx.mrcfile
from cctbx.array_family import flex
import os, sys
from libtbx.test_utils import approx_equal
from libtbx.utils import Sorry
from mmtbx.model import manager as model_manager
from iotbx import mrcfile

def exercise(file_name, out = sys.stdout):
  if not os.path.isfile(file_name):
    raise Sorry("Missing the file: %s" %(file_name)+"\n"+"Please run with phenix.python read_write_mrc.py my_mrcfile.mrc")

  print ("Reading from %s" %(file_name))
  from iotbx.map_manager import map_manager
  m = map_manager(file_name)

  print ("Header information from %s:" %(file_name))
  m.show_summary(out = out)

  map_data = m.map_data()
  crystal_symmetry = m.crystal_symmetry()
  unit_cell_parameters = m.crystal_symmetry().unit_cell().parameters()

  print ("\nMap origin: %s Extent %s"  %( map_data.origin(), map_data.all()))
  print ("Original unit cell, not just unit cell of part in this file): %s" %(
     str(unit_cell_parameters)))

  grid_point = (1, 2, 3)
  if map_data.origin() !=  (0, 0, 0): # make sure it is inside
    from scitbx.matrix import col
    grid_point = tuple (col(grid_point)+col(map_data.origin()))
  print ("\nValue of map_data at grid point %s: %.3f" %(str(grid_point),
    map_data[grid_point]))
  print ("Map data is %s" %(type(map_data)))

  random_position = (10, 5, 7.9)
  point_frac = crystal_symmetry.unit_cell().fractionalize(random_position)
  value_at_point_frac = map_data.eight_point_interpolation(point_frac)
  print ("Value of map_data at coordinates %s: %.3f" %(
      str(random_position), value_at_point_frac))

  map_data_as_float = map_data.as_float()
  print ("Map data as float is %s" %(type(map_data_as_float)))


  # make a little model
  sites_cart = flex.vec3_double( ((8, 10, 12), (14, 15, 16)))
  model = model_manager.from_sites_cart(
         atom_name = ' CA ',
         resname = 'ALA',
         chain_id = 'A',
         b_iso = 30.,
         occ = 1.,
         scatterer = 'C',
         sites_cart = sites_cart,
         crystal_symmetry = crystal_symmetry)


  # Move map and a model to place origin at (0, 0, 0)
  # If you don't care about original model and map, skip the deep_copy() below

  from iotbx.map_model_manager import map_model_manager
  mam = map_model_manager(
          map_manager =  m,
          model     = model.deep_copy(),
    )
  mam.box_all_maps_around_model_and_shift_origin()

  shifted_model = mam.model()
  shifted_map_data = mam.map_data()
  original_origin_grid_units = mam.original_origin_grid_units()
  original_origin_cart = mam.original_origin_cart()

  print ("\nOriginal map origin (grid units):", map_data.origin())
  print ("\nOriginal map origin (grid units, from mam):", mam.original_origin_grid_units())
  print ("\nOriginal map origin (cartesian):", mam.original_origin_cart())
  print ("Original model:\n", model.model_as_pdb())

  print ("Shifted map origin:", shifted_map_data.origin())
  print ("Shifted model:\n", shifted_model.model_as_pdb())


  mam.mask_all_maps_around_atoms(mask_atoms_atom_radius = 3,
     set_outside_to_mean_inside=True, soft_mask=False)
  print ("Mean before masking", mam.map_data().as_1d().min_max_mean().mean)
  assert approx_equal(mam.map_data().as_1d().min_max_mean().mean,
      -0.0585683621466)
  print ("Max before masking", mam.map_data().as_1d().min_max_mean().max)
  assert approx_equal(mam.map_data().as_1d().min_max_mean().max,
      -0.0585683621466)

  mam.mask_all_maps_around_atoms(mask_atoms_atom_radius = 3, soft_mask = True,
    soft_mask_radius = 5, set_outside_to_mean_inside=True)
  print ("Mean after first masking", mam.map_data().as_1d().min_max_mean().mean)
  assert approx_equal(mam.map_data().as_1d().min_max_mean().mean,
      -0.0585683621466)
  print ("Max after first masking", mam.map_data().as_1d().min_max_mean().max)
  assert approx_equal(mam.map_data().as_1d().min_max_mean().max,
      -0.0585683621466)
  mam.mask_all_maps_around_atoms(mask_atoms_atom_radius = 3,
     set_outside_to_mean_inside = True, soft_mask=False)
  print ("Mean after second masking", mam.map_data().as_1d().min_max_mean().mean)
  assert approx_equal(mam.map_data().as_1d().min_max_mean().mean,
     -0.0585683621466)
  print ("Max after second masking", mam.map_data().as_1d().min_max_mean().max)
  assert approx_equal(mam.map_data().as_1d().min_max_mean().max,
      -0.0585683621466)
  mam.mask_all_maps_around_edges( soft_mask_radius = 3)
  print ("Mean after masking edges", mam.map_data().as_1d().min_max_mean().mean)
  assert approx_equal(mam.map_data().as_1d().min_max_mean().mean,
      -0.0140564069152)
  print ("Max after masking edges", mam.map_data().as_1d().min_max_mean().max)
  assert approx_equal(mam.map_data().as_1d().min_max_mean().max,
      -0.0)


  print ("\nWriting map_data and model in shifted position (origin at 0, 0, 0)")

  output_file_name = 'shifted_map.ccp4'
  print ("Writing to %s" %(output_file_name))
  mrcfile.write_ccp4_map(
      file_name = output_file_name,
      crystal_symmetry = crystal_symmetry,
      map_data = shifted_map_data, )

  output_file_name = 'shifted_model.pdb'
  f = open(output_file_name, 'w')
  print (shifted_model.model_as_pdb(), file=f)
  f.close()


  print ("\nWriting map_data and model in original position (origin at %s)" %(
      str(mam.original_origin_grid_units())))

  output_file_name = 'new_map_original_position.ccp4'
  print ("Writing to %s" %(output_file_name))
  mrcfile.write_ccp4_map(
      file_name = output_file_name,
      crystal_symmetry = crystal_symmetry,
      map_data = shifted_map_data,
      origin_shift_grid_units = original_origin_grid_units)
  print (shifted_model.model_as_pdb())
  output_pdb_file_name = 'new_model_original_position.pdb'
  f = open(output_pdb_file_name, 'w')
  print (shifted_model.model_as_pdb(), file=f)
  f.close()

  # Write as mmcif
  output_cif_file_name = 'new_model_original_position.cif'
  f = open(output_cif_file_name, 'w')
  print (shifted_model.model_as_mmcif(),file = f)
  f.close()


  # Read the new map and model
  import iotbx.pdb
  new_model =  model_manager(
     model_input = iotbx.pdb.input(
         source_info = None,
         lines = flex.split_lines(open(output_pdb_file_name).read())),
         crystal_symmetry = crystal_symmetry)
  assert new_model.model_as_pdb() == model.model_as_pdb()

  new_model_from_cif =  model_manager(
     model_input = iotbx.pdb.input(
         source_info = None,
         lines = flex.split_lines(open(output_cif_file_name).read())),
         crystal_symmetry = crystal_symmetry)
  assert new_model_from_cif.model_as_pdb() == model.model_as_pdb()


  file_name = output_file_name
  print ("Reading from %s" %(file_name))
  new_map = iotbx.mrcfile.map_reader(file_name = file_name, verbose = False)
  print ("Header information from %s:" %(file_name))
  new_map.show_summary(out = out)
  assert new_map.map_data().origin() == m.map_data().origin()
  assert new_map.crystal_symmetry().is_similar_symmetry(m.crystal_symmetry())

  # make a map_model_manager with lots of maps and model and ncs
  from mmtbx.ncs.ncs import ncs
  ncs_object=ncs()
  ncs_object.set_unit_ncs()
  mam = map_model_manager(
          map_manager =  m,
          ncs_object =  ncs_object,
          map_manager_1 =  m.deep_copy(),
          map_manager_2 =  m.deep_copy(),
          extra_model_list =  [model.deep_copy(),model.deep_copy()],
          extra_model_id_list = ["model_1","model_2"],
          extra_map_manager_list =  [m.deep_copy(),m.deep_copy()],
          extra_map_id_list = ["extra_1","extra_2"],
          model     = model.deep_copy(),
    )


  # make a map_model_manager with lots of maps and model and ncs and run
  # with wrapping and ignore_symmetry_conflicts on
  from mmtbx.ncs.ncs import ncs
  ncs_object=ncs()
  ncs_object.set_unit_ncs()
  m.set_ncs_object(ncs_object.deep_copy())
  mam2 = map_model_manager(
          map_manager =  m.deep_copy(),
          ncs_object =  ncs_object.deep_copy(),
          map_manager_1 =  m.deep_copy(),
          map_manager_2 =  m.deep_copy(),
          extra_model_list =  [model.deep_copy(),model.deep_copy()],
          extra_model_id_list = ["model_1","model_2"],
          extra_map_manager_list =  [m.deep_copy(),m.deep_copy()],
          extra_map_id_list = ["extra_1","extra_2"],
          model     = model.deep_copy(),
          ignore_symmetry_conflicts = True,
          wrapping = m.wrapping(),
    )
  assert mam.map_manager().is_similar(mam2.map_manager())
  assert mam.map_manager().is_similar(mam2.map_manager_1())
  assert mam.map_manager().is_similar(mam2.extra_map_manager_list()[1])
  assert mam.model().shift_cart() == mam2.model().shift_cart()
  assert mam.model().shift_cart() == mam2.get_model_by_id('model_2').shift_cart()



  print ("OK")

if __name__ == "__main__":
  args = sys.argv[1:]
  if not args:
    import libtbx.load_env
    file_name = libtbx.env.under_dist(
      module_name = "iotbx",
      path = "ccp4_map/tst_input.map")
    args = [file_name]
  if libtbx.env.find_in_repositories(relative_path='chem_data') is not None:
    exercise(file_name = args[0])
  else:
    print('chem_data is not available, skipping')
from argparse import ArgumentParser
parser = ArgumentParser()
parser.add_argument("--plot", action='store_true')
args = parser.parse_args()

import numpy as np
from scipy.spatial.transform import Rotation
from scipy.stats import pearsonr
import pylab as plt

from cctbx import sgtbx
from rstbx.symmetry.constraints import parameter_reduction
from scitbx.array_family import flex
from scitbx.matrix import sqr
from scitbx.matrix import rec
from simtbx.diffBragg.nanoBragg_crystal import nanoBragg_crystal
from cctbx import uctbx
from simtbx.diffBragg.sim_data2 import SimData
from dxtbx.model.crystal import Crystal


# STEP 1:
# make a crystal and orient it randomly
ucell = (55, 66, 77, 90, 95, 90)
symbol = "P1211"
a_real, b_real, c_real = sqr(uctbx.unit_cell(ucell).orthogonalization_matrix()).transpose().as_list_of_lists()
#a_real, b_real, c_real = np.reshape(uctbx.unit_cell(ucell).orthogonalization_matrix(), (3,3)).T   #transpose().as_list_of_lists()
C = Crystal(a_real, b_real, c_real, symbol)

# random raotation
rotation = Rotation.random(num=1, random_state=1)[0]
Q = rec(rotation.as_quat(), n=(4, 1))
rot_ang, rot_axis = Q.unit_quaternion_as_axis_and_angle()
C.rotate_around_origin(rot_axis, rot_ang)
a_rot, b_rot, c_rot = C.get_real_space_vectors()

# STEP 2
# make the parameter reduction manager
point_group = sgtbx.space_group_info(symbol=symbol).group().build_derived_point_group()
S = parameter_reduction.symmetrize_reduce_enlarge(point_group)
S.set_orientation(np.hstack((a_real, b_real, c_real)), length_unit=1e-10)
X = S.forward_independent_parameters()
dX = S.forward_gradients()  # gradients in meters
n_ucell_params = len(X)

# STEP3: sanity check
B = S.backward_orientation(independent=X)
print("Number of parameters = %d" % n_ucell_params)
assert np.allclose(C.get_B(), B.reciprocal_matrix())
#Bstar = B.reciprocal_matrix()
print ("OK!")

# STEP4:
# make a nanoBragg crystal to pass to diffBragg
nbcryst = nanoBragg_crystal()
nbcryst.dxtbx_crystal = C
nbcryst.n_mos_domains = 1
nbcryst.thick_mm = 0.01
nbcryst.Ncells_abc = (7, 7, 7)

# STEP5: make an instance of diffBRagg, use the simData wrapper
SIM = SimData()
# overwrite the default detector with a smaller pixels one
SIM.detector = SimData.simple_detector(298, 0.1, (700, 700))
# FIXME: determine why setting detdist > 298 causes oversample to diverge...
SIM.crystal = nbcryst
SIM.instantiate_diffBragg(oversample=0)
# D is an instance of diffBragg with reasonable parameters
# and our dxtbx crystal created above
D = SIM.D

# STEP6:
# initialize the derivative managers for the unit cell parameters
for i_param in range(n_ucell_params):
    D.refine(3+i_param)
D.initialize_managers()
for i_param in range(n_ucell_params):
    dB_mat = dX[i_param]/1e10
    dB_mat = flex.double(
        (dB_mat[0], dB_mat[3], dB_mat[6],
         dB_mat[1], dB_mat[4], dB_mat[7],
         dB_mat[2], dB_mat[5], dB_mat[8]))
    D.set_ucell_derivative_matrix(3+i_param, dB_mat)

D.initialize_managers()
#D.show_params()

roi = ((0, 699), (0, 699))
rX = slice(roi[0][0], roi[0][1], 1)
rY = slice(roi[1][0], roi[1][1], 1)
D.region_of_interest = roi

# STEP7:
# compute the scattering and its derivative
D.add_diffBragg_spots()
img = D.raw_pixels_roi.as_numpy_array()
# reset all pixel values
D.raw_pixels *= 0
D.raw_pixels_roi *= 0

derivs = []
for i_param in range(n_ucell_params):
    analy_deriv = SIM.D.get_derivative_pixels(3+i_param).as_numpy_array()
    derivs.append(analy_deriv)

print X
print np.reshape(dX[3], (3, 3))
# STEP8
# iterate over the parameters and do a finite difference test for each one
for i_param in range(n_ucell_params):
    analy_deriv = derivs[i_param]
    diffs = []
    # parameter shifts:
    shifts = [1e-8 * (2**i) for i in range(1, 12, 2)]
    for i_shift, param_shift in enumerate(shifts):
        X2 = list(X)
        X2[i_param] += param_shift
        B2 = S.backward_orientation(independent=X2).direct_matrix()

        a2_real = B2[0], B2[1], B2[2]
        b2_real = B2[3], B2[4], B2[5]
        c2_real = B2[6], B2[7], B2[8]
        C2 = Crystal(a2_real, b2_real, c2_real, symbol)
        print("\tPeturbing parameter %d shift %d / %d" % (i_param, i_shift+1, len(shifts)))
        print("\tGround truth unit cell:")
        uc_1 = "%.3f, %.3f, %.3f, %.3f, %.3f, %.3f" % C.get_unit_cell().parameters()
        print("\t%s" % uc_1)
        print("\tPeturbed unit cell:")
        uc_2 = "%.3f, %.3f, %.3f, %.3f, %.3f, %.3f" % C2.get_unit_cell().parameters()
        print("\t%s" % uc_2)

        D.Bmatrix = C2.get_B()
        D.add_diffBragg_spots()

        img2 = D.raw_pixels_roi.as_numpy_array()

        # Simulate the derivative
        delta_param = X2[i_param] - X[i_param]
        # TODO: why is it necessary to flip the sign to get overlap ?
        finite_deriv = (img2-img) / param_shift
        finite_deriv2 = (img-img2) / param_shift

        bragg = img > 0.5
        r = pearsonr(analy_deriv[bragg].ravel(), finite_deriv2[bragg].ravel())[0]
        diffs.append(r)
        D.raw_pixels_roi *= 0
        D.raw_pixels *= 0
        if args.plot:
            plt.subplot(121)
            plt.imshow(finite_deriv2)
            plt.title("finite diff")
            plt.subplot(122)
            plt.imshow(analy_deriv)
            plt.title("analytical")
            plt.draw()
            plt.suptitle("Shift %d / %d\n ground truth cell=%s\nperturbed cell=%s"
                         % (i_shift+1, len(shifts), uc_1, uc_2))
            plt.pause(0.3)

    if args.plot:
        plt.close()
        plt.plot(shifts, diffs, 'o')
        title = "Unit cell parameter %d / %d" % (i_param+1, n_ucell_params)
        plt.title(title + "\nPearson corr between finite diff and analytical")
        plt.xlabel("unit cell shifts")
        plt.ylabel("Pearson corr")
        plt.show()

    # verify a high correlation for the smallest parameter shift
    print("Check high pearson R between analytical and finite diff")
    print("Pearson correlection at smallest parameter shift=%f" % diffs[0])
    assert(diffs[0] > .98), "%f" % diffs[0]
    # check monotonic decrease
    print("Fit polynomial and check monotonic decrease")
    trend = np.polyval(np.polyfit(shifts, diffs, 2), shifts)
    assert np.all(np.diff(zip(trend[:-1], trend[1:]), axis=1) <= 0)
print("OK!")

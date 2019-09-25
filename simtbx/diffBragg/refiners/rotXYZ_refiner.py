
import pylab as plt
import numpy as np

from scitbx.array_family import flex
from scitbx.matrix import col
from simtbx.diffBragg.refiners import PixelRefinement


class RefineRot(PixelRefinement):

    def __init__(self, spot_rois, abc_init, img, SimData_instance,
                 plot_images=False):
        """
        :param spot_rois:
        :param abc_init:
        :param img:
        :param SimData_instance:
        :param plot_images:
        """
        self.plot_images = plot_images
        self.spot_rois = spot_rois
        self.abc_init = abc_init
        self.img = img
        self.S = SimData_instance
        self.trad_conv = False
        self.trad_conv_eps = 0.05
        self.drop_conv_max_eps = 1e-5
        self.mn_iter = None
        self.mx_iter = None
        self.max_calls = 1000
        self.ignore_line_search = False

    def _setup(self):
        # total number of refinement parameters
        n_bg = 3*self.n_spots
        n_scale = 1
        n_rot = 3
        n_params = n_bg + n_rot + n_scale
        self.x = flex.double(n_params)

        # populate the x-array with initial values
        self._move_abc_init_to_x()
        self.x[-4] = 0  # initial delta rotation
        self.x[-3] = 0
        self.x[-2] = 0
        self.x[-1] = 1  # initial scale factor

        # setup the diffBragg instance
        self.D = self.S.D
        self.D.refine(0)  # rotX
        self.D.refine(1)  # rotY
        self.D.refine(2)  # rotZ
        self.D.initialize_managers()

    def _move_abc_init_to_x(self):
        for i in range(self.n_spots):
            self.x[i] = self.abc_init[i, 0]
            self.x[self.n_spots+i] = self.abc_init[i, 1]
            self.x[2*self.n_spots+i] = self.abc_init[i, 2]

    @property
    def x(self):
        return self._x

    @x.setter
    def x(self, val):
        self._x = val

    def _run_diffBragg_current(self, i_spot):
        self.D.region_of_interest = self.nanoBragg_rois[i_spot]
        self.D.set_value(0, self.thetaX)
        self.D.set_value(1, self.thetaY)
        self.D.set_value(2, self.thetaZ)
        self.D.add_diffBragg_spots()

    def _set_background_plane(self, i_spot):
        xr = self.xrel[i_spot]
        yr = self.yrel[i_spot]
        self.tilt_plane = xr*self.a + yr*self.b + self.c

    def _extract_pixel_data(self):
        self.dRotX = self.D.get_derivative_pixels(0)
        self.dRotX = self.dRotX.as_numpy_array()

        self.dRotY = self.D.get_derivative_pixels(1)
        self.dRotY = self.dRotY.as_numpy_array()

        self.dRotZ = self.D.get_derivative_pixels(2)
        self.dRotZ = self.dRotZ.as_numpy_array()

        self.model_bragg_spots = self.D.raw_pixels_roi.as_numpy_array()

    def _evaluate_averageI(self):
        """model_Lambda means expected intensity in the pixel"""
        self.model_Lambda = self.tilt_plane + self.scale_fac * self.model_bragg_spots

    def _unpack_params(self, i_spot):
        self.a = self.x[i_spot]
        self.b = self.x[self.n_spots + i_spot]
        self.c = self.x[self.n_spots*2 + i_spot]
        self.thetaX = self.x[self.n_spots*3]
        self.thetaY = self.x[self.n_spots*3+1]
        self.thetaZ = self.x[self.n_spots*3+2]
        self.scale_fac = self.x[-1]

    def _evaluate_log_averageI(self):
        # fix log(x<=0)
        self.log_Lambda = np.log(self.model_Lambda)
        self.log_Lambda[self.model_Lambda <= 0] = 0

    def compute_functional_and_gradients(self):
        f = 0
        g = flex.double(len(self.x))
        for i_spot in range(self.n_spots):

            self._unpack_params(i_spot)
            self._run_diffBragg_current(i_spot)
            self._set_background_plane(i_spot)
            self._extract_pixel_data()
            self._evaluate_averageI()
            self._evaluate_log_averageI()

            Imeas = self.roi_img[i_spot]

            f += (self.model_Lambda - Imeas*self.log_Lambda).sum()

            one_minus_k_over_Lambda = (1. - Imeas / self.model_Lambda)

            # compute gradients for background plane constants a,b,c
            xr = self.xrel[i_spot]  # fast scan pixels
            yr = self.yrel[i_spot]  # slow scan pixels
            g[i_spot] += (xr * one_minus_k_over_Lambda).sum()  # from handwritten notes
            g[self.n_spots + i_spot] += (yr * one_minus_k_over_Lambda).sum()
            g[self.n_spots*2 + i_spot] += one_minus_k_over_Lambda.sum()
            if self.plot_images:
                plt.cla()
                plt.subplot(121)
                im = plt.imshow(self.model_Lambda)
                #plt.imshow(self.model_bragg_spots > 1e-6)
                plt.subplot(122)
                im2 = plt.imshow(Imeas)
                im.set_clim(im2.get_clim())
                plt.suptitle("Spot %d / %d" % (i_spot+1, self.n_spots))
                #plt.draw()
                plt.show()
                #plt.pause(.2)

            # rotation derivative
            g[self.n_spots*3] += (one_minus_k_over_Lambda * (self.dRotX)).sum()
            g[self.n_spots*3+1] += (one_minus_k_over_Lambda * (self.dRotY)).sum()
            g[self.n_spots*3+2] += (one_minus_k_over_Lambda * (self.dRotZ)).sum()

            # scale factor derivative
            g[-1] += ((self.model_bragg_spots) * one_minus_k_over_Lambda).sum()

        self.D.raw_pixels *= 0
        self.print_step("LBFGS stp", f)
        return f, g

    def print_step(self, message, target):
        print ("%s %10.4f" % (message, target),
               "[", " ".join(["%9.6f" % a for a in self.x]), "]")

    def get_correction_misset(self, as_axis_angle_deg=False):
        """
        return the current state of the perturbation matrix
        :return: scitbx.matrix sqr
        """
        angles = self.x[-4:-1]
        x = col((-1, 0, 0))
        y = col((0, -1, 0))
        z = col((0, 0, -1))
        RX = x.axis_and_angle_as_r3_rotation_matrix(angles[0], deg=False)
        RY = y.axis_and_angle_as_r3_rotation_matrix(angles[1], deg=False)
        RZ = z.axis_and_angle_as_r3_rotation_matrix(angles[2], deg=False)
        M = RX*RY*RZ
        if as_axis_angle_deg:
            q = M.r3_rotation_matrix_as_unit_quaternion()
            rot_ang, rot_ax = q.unit_quaternion_as_axis_and_angle(deg=True)
            return rot_ang, rot_ax
        else:
            return M
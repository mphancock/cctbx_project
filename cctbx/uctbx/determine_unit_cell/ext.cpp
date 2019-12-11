#include <cctbx/boost_python/flex_fwd.h>
#include <boost/python/module.hpp>
#include <boost/python/def.hpp>
#include <cfloat>
#include <cctbx/uctbx/determine_unit_cell/NCDist.h>
#include <scitbx/array_family/tiny.h>
#include <scitbx/array_family/flex_types.h>
#include <scitbx/array_family/versa.h>
#include <scitbx/array_family/shared.h>
#include <scitbx/array_family/accessors/c_grid.h>
#include <omptbx/omp_or_stubs.h>
namespace af = scitbx::af;

using namespace boost::python;

namespace cctbx { namespace uctbx {

  double NCDist_wrapper(af::tiny<double,6> mm1,af::tiny<double,6> mm2){
    return NCDist(&mm1[0],&mm2[0]);
  }

  scitbx::af::versa<double, scitbx::af::c_grid<2> > NCDist_matrix(scitbx::af::shared<double> MM){
    int NN = MM.size()/6;
    af::versa<double, af::c_grid<2> > result( af::c_grid<2> (NN,NN));
    double* MM_ptr = MM.begin();
    double* result_ptr = result.begin();

    # pragma omp parallel
    {
    # pragma omp for
    for (int i = 0; i < NN; ++i) {
      af::tiny<double,6> mm1(&(MM_ptr[i*6]), &(MM_ptr[(i+1)*6]));
      for (int j = i+1; j < NN; ++j) {
        af::tiny<double,6> mm2(&(MM_ptr[j*6]), &(MM_ptr[(j+1)*6]));
        double metric = NCDist(&mm1[0],&mm2[0]);
        result_ptr[i*NN + j] = metric;
        result_ptr[j*NN + i] = metric;
      }
    }
    }
    return result;
  }

  scitbx::af::versa<double, scitbx::af::c_grid<2> > NCDist_flatten(scitbx::af::shared<double> MM){
    int NN = MM.size()/6;
    af::versa<double, af::c_grid<2> > result( af::c_grid<2> (NN,NN));
    double* MM_ptr = MM.begin();
    double* result_ptr = result.begin();
    // figure out the number of non-diagonal elements in an NN x NN square matrix
    int n_elements = (NN*NN-NN)/2;
    # pragma omp parallel
    {
    # pragma omp for
    for (int idx = 0; idx < n_elements; ++idx) {
      // Given idx, can we deduce the i and j upper-triangular coordinates?
      double quad_a = -0.5;
      double quad_b = (NN-0.5);
      double quad_c = -(double)(idx);
      double radical = std::sqrt(quad_b*quad_b - 4.*quad_a*quad_c);
      int i = (int)( (-quad_b + radical)/ (2.*quad_a) );
      int total_count_above_row_i=(NN*i)-((i*i-i)/2)-i;
      int j = idx - total_count_above_row_i + (i+1);
      // for the NCDist metric, pass in pointers to the two metrical matrices
      double metric = NCDist(&(MM_ptr[i*6]),&(MM_ptr[j*6]));
      result_ptr[i*NN + j] = metric;
      result_ptr[j*NN + i] = metric;
      }
    }
    return result;
  }

}}

// Contingent upon Andrews-Bernstein NCDist repository
# if HAVE_NCDIST
namespace ncdist2017 {
#include <NCDist.h>
#include <CS6Dist.h>
}

namespace cctbx { namespace uctbx {

  double NCDist2017_wrapper(af::tiny<double,6> mm1,af::tiny<double,6> mm2){
    return ncdist2017::NCDist(&mm1[0],&mm2[0]);
  }

  double CS6Dist_wrapper(af::tiny<double,6> mm1,af::tiny<double,6> mm2){
    return ncdist2017::CS6Dist(&mm1[0],&mm2[0]);
  }

  double CS6Dist_in_G6_wrapper(af::tiny<double,6> mm1,af::tiny<double,6> mm2){
    return ncdist2017::CS6Dist_in_G6(&mm1[0],&mm2[0]);
  }

  af::tiny<double,6> S6Dist_reduce_wrapper(af::tiny<double,6> mm1, std::string centering_symbol) {
    // stub
    return mm1;
  }

  scitbx::af::versa<double, scitbx::af::c_grid<2> > CS6Dist_in_G6_flatten(scitbx::af::shared<double> MM){
    int NN = MM.size()/6;
    af::versa<double, af::c_grid<2> > result( af::c_grid<2> (NN,NN));
    double* MM_ptr = MM.begin();
    double* result_ptr = result.begin();
    // figure out the number of non-diagonal elements in an NN x NN square matrix
    int n_elements = (NN*NN-NN)/2;
    # pragma omp parallel
    {
    # pragma omp for
    for (int idx = 0; idx < n_elements; ++idx) {
      // Given idx, can we deduce the i and j upper-triangular coordinates?
      double quad_a = -0.5;
      double quad_b = (NN-0.5);
      double quad_c = -(double)(idx);
      double radical = std::sqrt(quad_b*quad_b - 4.*quad_a*quad_c);
      int i = (int)( (-quad_b + radical)/ (2.*quad_a) );
      int total_count_above_row_i=(NN*i)-((i*i-i)/2)-i;
      int j = idx - total_count_above_row_i + (i+1);
      //
      double metric = ncdist2017::CS6Dist_in_G6(&(MM_ptr[i*6]),&(MM_ptr[j*6]));
      result_ptr[i*NN + j] = metric;
      result_ptr[j*NN + i] = metric;
      }
    }
    return result;
  }

}}
# endif // HAVE_NCDIST

BOOST_PYTHON_MODULE(determine_unit_cell_ext)
{
  def ("NCDist",&cctbx::uctbx::NCDist_wrapper);
  def ("NCDist_matrix",&cctbx::uctbx::NCDist_matrix);
  def ("NCDist_flatten",&cctbx::uctbx::NCDist_flatten);
# if HAVE_NCDIST
  def ("NCDist2017",&cctbx::uctbx::NCDist2017_wrapper);
  def ("CS6Dist",&cctbx::uctbx::CS6Dist_wrapper);
  def ("CS6Dist_in_G6",&cctbx::uctbx::CS6Dist_in_G6_wrapper,(arg("G6cell1"),arg("G6cell2")),
      "Use this in place of the NCDist wrapper when working with G6 arguments\n"
      "A G6 argument is [a.a, b.b, c.c, 2*b.c, 2*a.c, 2*a.b]\n"
      "It is assumed the arguments are primitive, Niggli reduced\n");
  def ("CS6Dist_in_G6_flatten",&cctbx::uctbx::CS6Dist_in_G6_flatten,(arg("G6")),
      "Obtain an NxN flex versa <double> containing S6 metrics from a list of N G6 vectors.\n"
      "The resulting matrix is symmetric.\n"
      "The G6 vectors [a.a, b.b, c.c, 2*b.c, 2*a.c, 2*a.b]\n"
      "are to be passed in as a flex.double containing 6*N elements.\n"
      "It is assumed the a,b,c vectors are primitive, Niggli reduced\n");
  def ("S6_reduce",&cctbx::uctbx::S6Dist_reduce_wrapper);
# endif // HAVE_NCDIST
}

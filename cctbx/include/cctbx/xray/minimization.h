#ifndef CCTBX_XRAY_MINIMIZATION_H
#define CCTBX_XRAY_MINIMIZATION_H

#include <cctbx/xray/scattering_dictionary.h>
#include <cctbx/xray/gradient_flags.h>
#include <cctbx/xray/packing_order.h>
#include <scitbx/array_family/block_iterator.h>

namespace cctbx { namespace xray { namespace minimization {

  template <typename XrayScattererType,
            typename FloatType>
  struct apply_shifts
  {
    af::shared<XrayScattererType> shifted_scatterers;
    af::shared<FloatType> mean_displacements;

    apply_shifts(
      uctbx::unit_cell const& unit_cell,
      af::const_ref<XrayScattererType> const& scatterers,
      xray::gradient_flags const& gradient_flags,
      af::const_ref<FloatType> const& shifts)
    {
      BOOST_STATIC_ASSERT(packing_order_convention == 1);
      typedef typename XrayScattererType::float_type sc_f_t;
      shifted_scatterers.reserve(scatterers.size());
      if (gradient_flags.u_iso && gradient_flags.sqrt_u_iso) {
        mean_displacements.resize(scatterers.size(), 0);
      }
      FloatType* mean_displacements_ptr = mean_displacements.begin();
      scitbx::af::const_block_iterator<FloatType> next_shifts(
        shifts, "Array of shifts is too small.");
      for(std::size_t i_sc=0;i_sc<scatterers.size();i_sc++) {
        XrayScattererType sc = scatterers[i_sc];
        if (gradient_flags.site) {
          sc.site += unit_cell.fractionalize(cartesian<sc_f_t>(next_shifts(3)));
        }
        if (!sc.anisotropic_flag) {
          if (gradient_flags.u_iso) {
            if (gradient_flags.sqrt_u_iso) {
              if (sc.u_iso < 0) {
                throw error(sc.report_negative_u_iso(__FILE__, __LINE__));
              }
              FloatType mean_displacement = std::sqrt(sc.u_iso)+next_shifts();
              sc.u_iso = scitbx::fn::pow2(mean_displacement);
              mean_displacements_ptr[i_sc] = mean_displacement;
            }
            else {
              sc.u_iso += next_shifts();
            }
          }
        }
        else {
          if (gradient_flags.u_aniso) {
            scitbx::sym_mat3<sc_f_t> u_cart = adptbx::u_star_as_u_cart(
              unit_cell, sc.u_star);
            u_cart += scitbx::sym_mat3<sc_f_t>(next_shifts(6));
            sc.u_star = adptbx::u_cart_as_u_star(unit_cell, u_cart);
          }
        }
        if (gradient_flags.occupancy) {
          sc.occupancy += next_shifts();
        }
        if (gradient_flags.fp) {
          sc.fp += next_shifts();
        }
        if (gradient_flags.fdp) {
          sc.fdp += next_shifts();
        }
        shifted_scatterers.push_back(sc);
      }
      if (!next_shifts.is_at_end()) {
        throw error("Array of shifts is too large.");
      }
    }
  };

  template <typename XrayScattererType,
            typename FloatType>
  void
  add_site_gradients(
    af::const_ref<XrayScattererType> const& scatterers,
    xray::gradient_flags const& gradient_flags,
    af::ref<FloatType> const& xray_gradients,
    af::const_ref<scitbx::vec3<FloatType> > const& site_gradients)
  {
    CCTBX_ASSERT(site_gradients.size() == scatterers.size());
    CCTBX_ASSERT(gradient_flags.site == true);
    BOOST_STATIC_ASSERT(packing_order_convention == 1);
    scitbx::af::block_iterator<FloatType> next_xray_gradients(
      xray_gradients, "Array of xray gradients is too small.");
    for(std::size_t i_sc=0;i_sc<scatterers.size();i_sc++) {
      XrayScattererType const& sc = scatterers[i_sc];
      FloatType* xg = next_xray_gradients(3);
      scitbx::vec3<FloatType> const& grsg = site_gradients[i_sc];
      for(std::size_t i=0;i<3;i++) xg[i] += grsg[i];
      if (!sc.anisotropic_flag) {
        if (gradient_flags.u_iso) {
          next_xray_gradients();
        }
      }
      else {
        if (gradient_flags.u_aniso) {
          next_xray_gradients(6);
        }
      }
      if (gradient_flags.occupancy) {
        next_xray_gradients();
      }
      if (gradient_flags.fp) {
        next_xray_gradients();
      }
      if (gradient_flags.fdp) {
        next_xray_gradients();
      }
    }
    if (!next_xray_gradients.is_at_end()) {
      throw error("Array of xray gradients is too large.");
    }
  }

  template <typename XrayScattererType,
            typename FloatType>
  af::shared<scitbx::vec3<FloatType> >
  extract_site_gradients(
    af::const_ref<XrayScattererType> const& scatterers,
    xray::gradient_flags const& gradient_flags,
    af::const_ref<FloatType> const& xray_gradients)
  {
    CCTBX_ASSERT(gradient_flags.site == true);
    BOOST_STATIC_ASSERT(packing_order_convention == 1);
    af::shared<scitbx::vec3<FloatType> > result(
      (af::reserve(scatterers.size())));
    scitbx::af::const_block_iterator<FloatType> next_xray_gradients(
      xray_gradients, "Array of xray gradients is too small.");
    for(std::size_t i_sc=0;i_sc<scatterers.size();i_sc++) {
      XrayScattererType const& sc = scatterers[i_sc];
      const FloatType* xg = next_xray_gradients(3);
      scitbx::vec3<FloatType> grsg;
      for(std::size_t i=0;i<3;i++) grsg[i] = xg[i];
      result.push_back(grsg);
      if (!sc.anisotropic_flag) {
        if (gradient_flags.u_iso) {
          next_xray_gradients();
        }
      }
      else {
        if (gradient_flags.u_aniso) {
          next_xray_gradients(6);
        }
      }
      if (gradient_flags.occupancy) {
        next_xray_gradients();
      }
      if (gradient_flags.fp) {
        next_xray_gradients();
      }
      if (gradient_flags.fdp) {
        next_xray_gradients();
      }
    }
    if (!next_xray_gradients.is_at_end()) {
      throw error("Array of xray gradients is too large.");
    }
    return result;
  }

  template <typename XrayScattererType,
            typename FloatType>
  void
  add_u_iso_gradients(
    af::const_ref<XrayScattererType> const& scatterers,
    xray::gradient_flags const& gradient_flags,
    af::ref<FloatType> const& xray_gradients,
    af::const_ref<FloatType> const& u_iso_gradients)
  {
    CCTBX_ASSERT(u_iso_gradients.size() == scatterers.size());
    CCTBX_ASSERT(gradient_flags.u_iso == true);
    BOOST_STATIC_ASSERT(packing_order_convention == 1);
    scitbx::af::block_iterator<FloatType> next_xray_gradients(
      xray_gradients, "Array of xray gradients is too small.");
    for(std::size_t i_sc=0;i_sc<scatterers.size();i_sc++) {
      XrayScattererType const& sc = scatterers[i_sc];
      if (gradient_flags.site) {
        next_xray_gradients(3);
      }
      if (!sc.anisotropic_flag) {
        if (gradient_flags.u_iso) {
          next_xray_gradients() += u_iso_gradients[i_sc];
        }
      }
      else {
        if (gradient_flags.u_aniso) {
          next_xray_gradients(6);
        }
      }
      if (gradient_flags.occupancy) {
        next_xray_gradients();
      }
      if (gradient_flags.fp) {
        next_xray_gradients();
      }
      if (gradient_flags.fdp) {
        next_xray_gradients();
      }
    }
    if (!next_xray_gradients.is_at_end()) {
      throw error("Array of xray gradients is too large.");
    }
  }

}}} // namespace cctbx::xray::targets

#endif // CCTBX_XRAY_MINIMIZATION_H

#ifndef IOTBX_MTZ_COLUMN_H
#define IOTBX_MTZ_COLUMN_H

#include <iotbx/mtz/dataset.h>

namespace iotbx { namespace mtz {

  class column
  {
    public:
      column() {}

      column(dataset const& mtz_dataset, int i_column)
      :
        mtz_dataset_(mtz_dataset),
        i_column_(i_column)
      {
        CCTBX_ASSERT(i_column >= 0);
        CCTBX_ASSERT(i_column < mtz_dataset.n_columns());
      }

      dataset
      mtz_dataset() const { return mtz_dataset_; }

      int
      i_column() const { return i_column_; }

      crystal
      mtz_crystal() const { return mtz_dataset_.mtz_crystal(); }

      object
      mtz_object() const { return mtz_crystal().mtz_object(); }

      CMtz::MTZCOL*
      ptr() const
      {
        CCTBX_ASSERT(mtz_dataset_.n_columns() > i_column_);
        return CMtz::MtzIcolInSet(mtz_dataset_.ptr(), i_column_);
      }

      const char*
      label() const { return ptr()->label; }

      const char*
      type() const { return ptr()->type; }

      bool
      is_active() const { return (ptr()->active != 0); }

      std::string
      path() const
      {
        boost::shared_ptr<char>
          p(CMtz::MtzColPath(mtz_object().ptr(), ptr()), free);
        return std::string(p.get());
      }

      column
      lookup_other(const char* label) const
      {
        return mtz_object().lookup_column(label);
      }

      float const&
      float_datum(int i) const { return ptr()->ref[i]; }

      bool
      is_ccp4_nan(int i) const { return mtz::is_ccp4_nan(float_datum(i)); }

      int
      int_datum(int i) const { return static_cast<int>(float_datum(i)); }

      int
      n_valid_values() const
      {
        int result = 0;
        int n_refl = mtz_object().n_reflections();
        for(int i=0;i<n_refl;i++) {
          if (!is_ccp4_nan(i)) result += 1;
        }
        return result;
      }

    protected:
      dataset mtz_dataset_;
      int i_column_;
  };

  class hkl_columns : public af::tiny<column, 3>
  {
    public:
      hkl_columns() {}

      hkl_columns(column const& h, column const& k, column const& l)
      :
        af::tiny<column, 3>(h, k, l)
      {}

      cctbx::miller::index<>
      get_miller_index(int i) const
      {
        return cctbx::miller::index<>(
          this->elems[0].int_datum(i),
          this->elems[1].int_datum(i),
          this->elems[2].int_datum(i));
      }
  };

  inline
  af::shared<column>
  dataset::columns() const
  {
    af::shared<column> result((af::reserve(n_columns())));
    for(int i_column=0;i_column<n_columns();i_column++) {
      result.push_back(column(*this, i_column));
    }
    return result;
  }

  inline
  column
  object::lookup_column(const char* label) const
  {
    for(int i_crystal=0;i_crystal<n_crystals();i_crystal++) {
      crystal x(*this, i_crystal);
      for(int i_dataset=0;i_dataset<x.n_datasets();i_dataset++) {
        dataset s(x, i_dataset);
        for(int i_column=0;i_column<s.n_columns();i_column++) {
          column c(s, i_column);
          if (CMtz::MtzPathMatch(label, c.label())) {
            return c;
          }
        }
      }
    }
    throw cctbx::error(std::string("Unknown MTZ column label: ") + label);
  }

  inline
  hkl_columns
  object::lookup_hkl_columns() const
  {
    return hkl_columns(
      lookup_column("H"),
      lookup_column("K"),
      lookup_column("L"));
  }

  namespace detail {
    inline
    std::complex<double>
    polar_deg(double ampl, double phi)
    {
      return std::polar(ampl, phi*scitbx::constants::pi_180);
    }
  }

  inline
  integer_group
  object::extract_integers(
    const char* column_label)
  {
    int n_refl = n_reflections();
    integer_group result(n_refl);
    hkl_columns hkl = lookup_hkl_columns();
    column data(lookup_column(column_label));
    for(int i=0;i<n_refl;i++) {
      if (!data.is_ccp4_nan(i)) {
        result.indices.push_back(hkl.get_miller_index(i));
        result.data.push_back(data.int_datum(i));
      }
    }
    return result;
  }

  inline
  real_group
  object::extract_reals(
    const char* column_label)
  {
    int n_refl = n_reflections();
    real_group result(n_refl);
    hkl_columns hkl = lookup_hkl_columns();
    column data(lookup_column(column_label));
    for(int i=0;i<n_refl;i++) {
      if (!data.is_ccp4_nan(i)) {
        result.indices.push_back(hkl.get_miller_index(i));
        result.data.push_back(data.float_datum(i));
      }
    }
    return result;
  }

  inline
  real_group
  object::extract_reals_anomalous(
    const char* column_label_plus,
    const char* column_label_minus)
  {
    int n_refl = n_reflections();
    real_group result(2*n_refl);
    hkl_columns hkl = lookup_hkl_columns();
    column data_plus(lookup_column(column_label_plus));
    column data_minus(lookup_column(column_label_minus));
    for(int i=0;i<n_refl;i++) {
      if (!data_plus.is_ccp4_nan(i)) {
        result.indices.push_back(hkl.get_miller_index(i));
        result.data.push_back(data_plus.float_datum(i));
      }
      if (!data_minus.is_ccp4_nan(i)) {
        result.indices.push_back(-hkl.get_miller_index(i));
        result.data.push_back(data_minus.float_datum(i));
      }
    }
    return result;
  }

  inline
  hl_group
  object::extract_hls(
    const char* column_label_a,
    const char* column_label_b,
    const char* column_label_c,
    const char* column_label_d)
  {
    int n_refl = n_reflections();
    hl_group result(n_refl);
    hkl_columns hkl = lookup_hkl_columns();
    column data_a(lookup_column(column_label_a));
    column data_b(lookup_column(column_label_b));
    column data_c(lookup_column(column_label_c));
    column data_d(lookup_column(column_label_d));
    for(int i=0;i<n_refl;i++) {
      if (   data_b.is_ccp4_nan(i) != data_a.is_ccp4_nan(i)
          || data_c.is_ccp4_nan(i) != data_a.is_ccp4_nan(i)
          || data_d.is_ccp4_nan(i) != data_a.is_ccp4_nan(i)) {
        throw cctbx::error(std::string(
          "Unexpected NAN while extracting complex array from columns: ")
          + column_label_a + ", "
          + column_label_b + ", "
          + column_label_c + ", "
          + column_label_d);
      }
      if (!data_a.is_ccp4_nan(i)) {
        result.indices.push_back(hkl.get_miller_index(i));
        result.data.push_back(cctbx::hendrickson_lattman<>(
          data_a.float_datum(i),
          data_b.float_datum(i),
          data_c.float_datum(i),
          data_d.float_datum(i)));
      }
    }
    return result;
  }

  inline
  observations_group
  object::extract_observations(
    const char* column_label_data,
    const char* column_label_sigmas)
  {
    int n_refl = n_reflections();
    observations_group result(n_refl);
    hkl_columns hkl = lookup_hkl_columns();
    column data(lookup_column(column_label_data));
    column sigmas(lookup_column(column_label_sigmas));
    for(int i=0;i<n_refl;i++) {
      if (data.is_ccp4_nan(i) != sigmas.is_ccp4_nan(i)) {
        throw cctbx::error(std::string(
          "Unexpected NAN while extracting observation array from columns: ")
          + column_label_data + ", " + column_label_sigmas);
      }
      if (!data.is_ccp4_nan(i)) {
        result.indices.push_back(hkl.get_miller_index(i));
        result.data.push_back(data.float_datum(i));
        result.sigmas.push_back(sigmas.float_datum(i));
      }
    }
    return result;
  }

  inline
  observations_group
  object::extract_observations_anomalous(
    const char* column_label_data_plus,
    const char* column_label_sigmas_plus,
    const char* column_label_data_minus,
    const char* column_label_sigmas_minus)
  {
    int n_refl = n_reflections();
    observations_group result(2*n_refl);
    hkl_columns hkl = lookup_hkl_columns();
    column data_plus(lookup_column(column_label_data_plus));
    column sigmas_plus(lookup_column(column_label_sigmas_plus));
    column data_minus(lookup_column(column_label_data_minus));
    column sigmas_minus(lookup_column(column_label_sigmas_minus));
    for(int i=0;i<n_refl;i++) {
      if (data_plus.is_ccp4_nan(i) != sigmas_plus.is_ccp4_nan(i)) {
        throw cctbx::error(std::string(
          "Unexpected NAN while extracting observation array from columns: ")
          + column_label_data_plus + ", " + column_label_sigmas_plus);
      }
      if (!data_plus.is_ccp4_nan(i)) {
        result.indices.push_back(hkl.get_miller_index(i));
        result.data.push_back(data_plus.float_datum(i));
        result.sigmas.push_back(sigmas_plus.float_datum(i));
      }
      if (data_minus.is_ccp4_nan(i) != sigmas_minus.is_ccp4_nan(i)) {
        throw cctbx::error(std::string(
          "Unexpected NAN while extracting observation array from columns: ")
          + column_label_data_minus + ", " + column_label_sigmas_minus);
      }
      if (!data_minus.is_ccp4_nan(i)) {
        result.indices.push_back(-hkl.get_miller_index(i));
        result.data.push_back(data_minus.float_datum(i));
        result.sigmas.push_back(sigmas_minus.float_datum(i));
      }
    }
    return result;
  }

  /*! http://www.ccp4.ac.uk/dist/html/mtzMADmod.html
        F(+) = F + 0.5*D
        F(-) = F - 0.5*D
        SIGF(+) = sqrt( SIGF**2 + 0.25*SIGD**2 )
        SIGF(-) = SIGF(+)
   */
  inline
  observations_group
  object::extract_delta_anomalous(
    const char* column_label_f_data,
    const char* column_label_f_sigmas,
    const char* column_label_d_data,
    const char* column_label_d_sigmas)
  {
    int n_refl = n_reflections();
    observations_group result(2*n_refl);
    hkl_columns hkl = lookup_hkl_columns();
    column f_data(lookup_column(column_label_f_data));
    column f_sigmas(lookup_column(column_label_f_sigmas));
    column d_data(lookup_column(column_label_d_data));
    column d_sigmas(lookup_column(column_label_d_sigmas));
    for(int i=0;i<n_refl;i++) {
      if (   f_sigmas.is_ccp4_nan(i) != f_data.is_ccp4_nan(i)
          || d_sigmas.is_ccp4_nan(i) != d_data.is_ccp4_nan(i)
          || (f_data.is_ccp4_nan(i) && !d_data.is_ccp4_nan(i))) {
        throw cctbx::error(std::string(
          "Unexpected NAN while extracting complex array from columns: ")
          + column_label_f_data   + ", "
          + column_label_f_sigmas + ", "
          + column_label_d_data   + ", "
          + column_label_d_sigmas);
      }
      if (!f_data.is_ccp4_nan(i)) {
        result.indices.push_back(hkl.get_miller_index(i));
        double fd = f_data.float_datum(i);
        double fs = f_sigmas.float_datum(i);
        if (d_data.is_ccp4_nan(i)) {
          result.data.push_back(fd);
          result.sigmas.push_back(fs);
        }
        else {
          double ddh = d_data.float_datum(i) * .5;
          double dsh = d_sigmas.float_datum(i) * .5;
          double s = std::sqrt(fs*fs + dsh*dsh);
          result.indices.push_back(-hkl.get_miller_index(i));
          result.data.push_back(fd + ddh);
          result.data.push_back(fd - ddh);
          result.sigmas.push_back(std::sqrt(s));
          result.sigmas.push_back(std::sqrt(s));
        }
      }
    }
    return result;
  }

  inline
  complex_group
  object::extract_complex(
    const char* column_label_ampl,
    const char* column_label_phi)
  {
    int n_refl = n_reflections();
    complex_group result(n_refl);
    hkl_columns hkl = lookup_hkl_columns();
    column data_ampl(lookup_column(column_label_ampl));
    column data_phi(lookup_column(column_label_phi));
    for(int i=0;i<n_refl;i++) {
      if (data_ampl.is_ccp4_nan(i) != data_phi.is_ccp4_nan(i)) {
        throw cctbx::error(std::string(
          "Unexpected NAN while extracting complex array from columns: ")
          + column_label_ampl + ", " + column_label_phi);
      }
      if (!data_ampl.is_ccp4_nan(i)) {
        result.indices.push_back(hkl.get_miller_index(i));
        result.data.push_back(detail::polar_deg(
          data_ampl.float_datum(i), data_phi.float_datum(i)));
      }
    }
    return result;
  }

  inline
  complex_group
  object::extract_complex_anomalous(
    const char* column_label_ampl_plus,
    const char* column_label_phi_plus,
    const char* column_label_ampl_minus,
    const char* column_label_phi_minus)
  {
    int n_refl = n_reflections();
    complex_group result(n_refl);
    hkl_columns hkl = lookup_hkl_columns();
    column data_ampl_plus(lookup_column(column_label_ampl_plus));
    column data_phi_plus(lookup_column(column_label_phi_plus));
    column data_ampl_minus(lookup_column(column_label_ampl_minus));
    column data_phi_minus(lookup_column(column_label_phi_minus));
    for(int i=0;i<n_refl;i++) {
      if (data_ampl_plus.is_ccp4_nan(i) != data_phi_plus.is_ccp4_nan(i)) {
        throw cctbx::error(std::string(
          "Unexpected NAN while extracting complex array from columns: ")
          + column_label_ampl_plus + ", " + column_label_phi_plus);
      }
      if (!data_ampl_plus.is_ccp4_nan(i)) {
        result.indices.push_back(hkl.get_miller_index(i));
        result.data.push_back(detail::polar_deg(
          data_ampl_plus.float_datum(i), data_phi_plus.float_datum(i)));
      }
      if (data_ampl_minus.is_ccp4_nan(i) != data_phi_minus.is_ccp4_nan(i)) {
        throw cctbx::error(std::string(
          "Unexpected NAN while extracting complex array from columns: ")
          + column_label_ampl_minus + ", " + column_label_phi_minus);
      }
      if (!data_ampl_minus.is_ccp4_nan(i)) {
        result.indices.push_back(-hkl.get_miller_index(i));
        result.data.push_back(detail::polar_deg(
          data_ampl_minus.float_datum(i), data_phi_minus.float_datum(i)));
      }
    }
    return result;
  }

}} // namespace iotbx::mtz

#endif // IOTBX_MTZ_COLUMN_H

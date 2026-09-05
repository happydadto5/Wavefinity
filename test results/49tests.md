# Wavefinity UI Testing Report - Failures Only
**Date:** September 4, 2026  
**Tests Conducted:** 40 different UI interactions  
**Issues Found:** 4  

---

## Issue 1: Decimal Input Validation - Misleading UX
**Location:** Units X and Units Y input fields  
**Test:** Tests 33-35  
**Severity:** Medium

**Problem:**
- Fields accept decimal values (2.5, 0.1) but then fail validation
- Error: "box X must be a whole multiple of the 8 mm grid..."
- Invalid value remains in field with no immediate feedback
- User enters bad data, then discovers it's not allowed

**Fix:** Restrict to whole numbers or validate on blur immediately

---

## Issue 2: Label Validation Error - Wrong Location
**Location:** Label text input field → error shows in 3D preview panel  
**Test:** Test 40  
**Severity:** Low-Medium

**Problem:**
- Validation error for label text appears in 3D preview panel (far right)
- Error: "TEST LABEL will not fit on this floor either way round..."
- Error is far from input field where user is typing
- Poor discoverability

**Fix:** Display error message adjacent to the input field

---

## Issue 3: Inconsistent Height Validation
**Location:** Height vs Height mm fields  
**Test:** Tests 14, 30  
**Severity:** Low

**Problem:**
- Height = 0 → shows error "Z must be a positive finite number"
- Height mm (Post) = 0 → silently hides posts, no error
- Inconsistent validation behavior across similar fields

**Fix:** Standardize validation rules for all height fields

---

## Issue 4: Persistent Validation Error State
**Location:** Pocket support Width/Depth fields  
**Test:** Tests 26-27  
**Severity:** Low

**Problem:**
- Width = 0 triggers error: "pocket will and depth must have a positive shell"
- Changing Depth to -5 does NOT clear error
- Error persists despite user modifying the state
- Unclear if correction worked

**Fix:** Implement real-time re-validation; error should clear when constraints satisfied

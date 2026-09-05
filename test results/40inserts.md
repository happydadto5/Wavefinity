# Wavefinity Interior Supports (Inserts) Testing Report
**Date:** September 4, 2026  
**Tests Conducted:** 40 interior support parameter tests  
**Focus:** Cradle, Nest, Bore, Post, Pocket, Divider edge cases  
**Failures Documented:** Only issues found  

---

## Summary
Tested each of 6 interior support types with extreme values, boundary conditions, and invalid combinations. Most parameter validation works correctly. Found **6 issues** related to parameter handling and validation.

---

## Failures Found

### Issue 1: Pocket Width = 0 - Error Persists After Changes
**Support Type:** Pocket  
**Parameter:** Width mm  
**Test Case:** Set Width to 0, then change Depth  
**Problem:** 
- Width = 0 shows error: "pocket will and depth must have a positive shell"
- Changing Depth value does NOT clear the error
- Error persists in preview even though user modified the problematic state
- Unclear if error applies to just Width or to the combination

**Expected:** Real-time re-validation should clear error when constraints satisfied

---

### Issue 2: Bore/Nest/Pocket Center Coordinates No Bounds Checking
**Support Type:** Bore, Nest, Pocket  
**Parameters:** Center X, Center Y  
**Test Cases:** 
- Center X = 1000 (way beyond bin width)
- Center Y = 1000 (way beyond bin depth)
**Problem:**
- No validation prevents placing support center far outside the bin
- Support silently renders outside visible bounds
- No error message or warning
- User gets no feedback that positioning is invalid

**Expected:** Validate that Center X/Y are within bin boundaries, show error if not

---

### Issue 3: Post Quantity = 0 - No Error, Posts Disappear Silently
**Support Type:** Post  
**Parameter:** Quantity  
**Test Case:** Set Quantity to 0  
**Problem:**
- Quantity = 0 is accepted without error
- Posts disappear from preview silently
- No warning message
- Inconsistent with validation for Quantity = 0 on Divider (which shows "must be positive")

**Expected:** Either reject 0 with error message, or at least show warning

**Related:** Divider Quantity = 0 shows: "Z must be a positive finite number" - inconsistent behavior

---

### Issue 4: Divider Angle > 360 - No Clamping or Warning
**Support Type:** Divider  
**Parameter:** Angle  
**Test Case:** Set Angle to 720  
**Problem:**
- Angle = 720 is accepted
- Preview shows unexpected geometry (double-wrapped angle)
- No validation warning
- Should either clamp to 0-360 or warn user

**Expected:** Either clamp angle to 0-360, or validate and show error

---

### Issue 5: Post Taper Negative - Renders Inverted, No Error
**Support Type:** Post  
**Parameter:** Taper mm  
**Test Case:** Set Taper to -5  
**Problem:**
- Negative taper value accepted without error
- Post renders with inverted/upside-down taper geometry
- Likely not intended behavior
- No validation prevents impossible geometry

**Expected:** Only allow positive taper values, show error if negative entered

---

### Issue 6: Pocket Recess Extremely Large Values Cause Geometry Errors
**Support Type:** Pocket  
**Parameter:** Recess mm  
**Test Case:** Set Recess to 1000 (larger than pocket height)  
**Problem:**
- No validation checks that Recess <= Height
- Renders degenerate geometry
- No error message
- Silently produces invalid/broken model

**Expected:** Validate Recess <= Height, show error if violated

---

## Tests That Passed ✓

**Cradle Support:**
- ✓ All Center X/Y values render correctly (including negatives clamped to valid range)
- ✓ Width/Depth parameter changes update preview correctly
- ✓ Quantity changes work (though no validation for Quantity=0)

**Nest Support:**
- ✓ Parameter changes update preview
- ✓ Width and Depth fields accept reasonable values

**Bore Support:**
- ✓ Diameter changes render correctly
- ✓ Quantity updates multiple holes
- ✓ Spacing/Gap parameters work

**Divider Support:**
- ✓ Direction toggle (X/Y) works correctly
- ✓ Width parameter respected
- ✓ Quantity auto-calculation works
- ✓ Spacing modes work (Fills evenly, etc.)

---

## Validation Summary

| Support | Parameter | Validates | Issue |
|---------|-----------|-----------|-------|
| Pocket | Width = 0 | YES | Error doesn't clear |
| Pocket | Recess > Height | NO | No validation |
| Bore/Nest/Pocket | Center X/Y out of bounds | NO | No validation |
| Post | Quantity = 0 | NO | Silent fail |
| Post | Taper < 0 | NO | Inverted geometry |
| Divider | Angle > 360 | NO | No clamping |
| Cradle | Quantity = 0 | INCONSISTENT | Different from Post/Divider |

---

## Root Causes

1. **Inconsistent validation** - Some supports validate Quantity=0, others don't
2. **Missing boundary checks** - Center positions not validated against bin size
3. **Silent failures** - Invalid parameters accepted, produce broken geometry silently
4. **Persistent error state** - Error messages don't update on related field changes
5. **No parameter constraints** - Negative/extreme values accepted where they shouldn't be
6. **Missing cross-field validation** - Recess not validated against Height

---

## Recommended Fixes

### High Priority
1. Add bounds validation for Center X/Y (must be within [0, bin_width] and [0, bin_depth])
2. Standardize Quantity validation - either all enforce positive, or all allow 0 silently
3. Implement real-time cross-field validation (Recess <= Height for Pocket)

### Medium Priority
4. Add parameter constraints to numeric inputs (min/max, step)
5. Validate negative values where they don't make sense (Taper, Gap)
6. Clamp or validate Angle to 0-360 range for Divider

### Low Priority
7. Show validation errors in UI near the problematic field
8. Implement live error message updates as user modifies fields

# Treatment – Decision Logic

Roles: Patient, Doctor, Pharmacist

- Patient: initiates `complaint(id, symptom)`; on `reassurance` or `filledRx`, records `done`.
- Doctor: on `complaint`, chooses exactly one of:
  - `reassurance` (sets `done`), or
  - `prescription` (sets `rx`).
    Choice is randomized (≈50/50) to expose both maximal enactments.
- Pharmacist: on `prescription`, sends `filledRx` to Patient.

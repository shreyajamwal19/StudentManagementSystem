-- Schema for System A (marks_a, record_versions_a) and System B (marks_b, record_versions_b).
-- Both systems share the same reference tables and have identical structure and constraints.

CREATE TABLE faculty (
  faculty_id VARCHAR(10) PRIMARY KEY
);

CREATE TABLE courses (
  course_id  VARCHAR(10) PRIMARY KEY,
  faculty_id VARCHAR(10) NOT NULL REFERENCES faculty(faculty_id)   -- course-specific faculty assignment
);

CREATE TABLE assessments (
  assessment_id VARCHAR(20) PRIMARY KEY,
  max_marks     INTEGER NOT NULL CHECK (max_marks > 0)
);

CREATE TABLE students (
  student_id VARCHAR(10) PRIMARY KEY,
  pseudonym  CHAR(64) NOT NULL UNIQUE          -- HMAC-SHA256(pepper, student_id); this is what goes on-chain
);

CREATE TABLE users (
  user_id       BIGSERIAL PRIMARY KEY,
  username      VARCHAR(50) NOT NULL UNIQUE,
  password_hash VARCHAR(100) NOT NULL,
  role          VARCHAR(20) NOT NULL CHECK (role IN ('FACULTY','MODERATOR','EXAM_ADMIN','STUDENT')),
  faculty_id    VARCHAR(10) REFERENCES faculty(faculty_id),
  student_id    VARCHAR(10) REFERENCES students(student_id),
  besu_address  CHAR(42),
  CHECK (role <> 'FACULTY' OR faculty_id IS NOT NULL),
  CHECK (role <> 'STUDENT' OR student_id IS NOT NULL)
);

CREATE OR REPLACE FUNCTION enforce_marks_within_max() RETURNS trigger AS $$
DECLARE m INTEGER;
BEGIN
  SELECT max_marks INTO m FROM assessments WHERE assessment_id = NEW.assessment_id;
  IF NEW.marks_obtained > m THEN
    RAISE EXCEPTION 'marks_obtained % exceeds max_marks % for %', NEW.marks_obtained, m, NEW.assessment_id;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

-- ---- System A -------------------------------------------------------------
CREATE TABLE marks_a (
  record_id      VARCHAR(12) PRIMARY KEY,
  student_id     VARCHAR(10) NOT NULL REFERENCES students(student_id),
  course_id      VARCHAR(10) NOT NULL REFERENCES courses(course_id),
  assessment_id  VARCHAR(20) NOT NULL REFERENCES assessments(assessment_id),
  faculty_id     VARCHAR(10) NOT NULL REFERENCES faculty(faculty_id),
  marks_obtained NUMERIC(4,1) NOT NULL CHECK (marks_obtained >= 0),
  status         VARCHAR(24) NOT NULL CHECK (status IN
                 ('Entered','Submitted','Moderated','Approved','Locked','CorrectionRequested','CorrectionAuthorized')),
  version_no     INTEGER NOT NULL DEFAULT 1 CHECK (version_no >= 1),
  recorded_at    TIMESTAMP NOT NULL,           -- original CSV Timestamp, preserved as given
  UNIQUE (student_id, course_id, assessment_id)
);
CREATE TRIGGER marks_a_max BEFORE INSERT OR UPDATE ON marks_a
  FOR EACH ROW EXECUTE FUNCTION enforce_marks_within_max();

CREATE TABLE record_versions_a (
  record_id      VARCHAR(12) NOT NULL REFERENCES marks_a(record_id),
  version_no     INTEGER NOT NULL,
  action         VARCHAR(30) NOT NULL,
  marks_obtained NUMERIC(4,1) NOT NULL,
  status         VARCHAR(24) NOT NULL,
  actor          VARCHAR(50) NOT NULL,
  record_hash    CHAR(64),                      -- unused (NULL) in System A
  prev_hash      CHAR(64),
  created_at     TIMESTAMP NOT NULL,
  PRIMARY KEY (record_id, version_no)
);

-- ---- System B -------------------------------------------------------------
CREATE TABLE marks_b (LIKE marks_a INCLUDING DEFAULTS INCLUDING CONSTRAINTS);
ALTER TABLE marks_b ADD PRIMARY KEY (record_id);
ALTER TABLE marks_b ADD FOREIGN KEY (student_id)    REFERENCES students(student_id);
ALTER TABLE marks_b ADD FOREIGN KEY (course_id)     REFERENCES courses(course_id);
ALTER TABLE marks_b ADD FOREIGN KEY (assessment_id) REFERENCES assessments(assessment_id);
ALTER TABLE marks_b ADD FOREIGN KEY (faculty_id)    REFERENCES faculty(faculty_id);
ALTER TABLE marks_b ADD UNIQUE (student_id, course_id, assessment_id);
CREATE TRIGGER marks_b_max BEFORE INSERT OR UPDATE ON marks_b
  FOR EACH ROW EXECUTE FUNCTION enforce_marks_within_max();

CREATE TABLE record_versions_b (
  record_id      VARCHAR(12) NOT NULL REFERENCES marks_b(record_id),
  version_no     INTEGER NOT NULL,
  action         VARCHAR(30) NOT NULL,
  marks_obtained NUMERIC(4,1) NOT NULL,
  status         VARCHAR(24) NOT NULL,
  actor          VARCHAR(50) NOT NULL,
  record_hash    CHAR(64) NOT NULL,             -- SHA-256 of canonical record; prev_hash links to version_no-1 of SAME record
  prev_hash      CHAR(64) NOT NULL,
  created_at     TIMESTAMP NOT NULL,
  PRIMARY KEY (record_id, version_no)
);

-- Mirror of Besu receipts (convenience only; verification re-reads Besu).
CREATE TABLE chain_anchor (
  id             BIGSERIAL PRIMARY KEY,
  record_id      VARCHAR(12) NOT NULL,
  version_no     INTEGER NOT NULL,
  action         VARCHAR(30) NOT NULL,
  record_hash    CHAR(64) NOT NULL,
  prev_hash      CHAR(64) NOT NULL,
  tx_hash        CHAR(66) NOT NULL,
  block_number   BIGINT,
  actor_address  CHAR(42),
  batch_id       VARCHAR(40),                   -- set for batch-anchored initial import
  submit_ms      DOUBLE PRECISION,
  confirm_ms     DOUBLE PRECISION,
  created_at     TIMESTAMP NOT NULL DEFAULT now(),
  FOREIGN KEY (record_id, version_no) REFERENCES record_versions_b(record_id, version_no)
);

-- Ordinary application audit log (both systems).
CREATE TABLE audit_log (
  id         BIGSERIAL PRIMARY KEY,
  system     CHAR(1) NOT NULL CHECK (system IN ('A','B')),
  record_id  VARCHAR(12),
  action     VARCHAR(30) NOT NULL,
  actor      VARCHAR(50) NOT NULL,
  old_value  TEXT,
  new_value  TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_marks_a_student ON marks_a(student_id);
CREATE INDEX idx_marks_b_student ON marks_b(student_id);
CREATE INDEX idx_marks_a_course ON marks_a(course_id);
CREATE INDEX idx_marks_b_course ON marks_b(course_id);

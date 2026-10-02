export type User = {
  id: string
  email: string
  name: string
  role: string
  organization_name: string
}
export type Candidate = {
  id: string
  name: string
  email: string | null
  role_title: string
  stage: string
  experience: string
  skills: string[]
  current_ctc: string
  expected_ctc: string
  availability: string
  created_at: string
  score: number | null
  job_id: string | null
}
export type Job = {
  id: string
  title: string
  location: string
  employment_type: string
  status: string
  description: string
  requirements: {
    skill: string
    category: string
    weight: number
    min_evidence_level: number
  }[]
  applications_count: number
}
export type Interview = {
  id: string
  candidate_id: string
  candidate_name: string
  candidate_email: string | null
  interviewer_id: string | null
  title: string
  scheduled_for: string
  duration_minutes: number
  timezone: string
  meeting_method: string
  location_or_link: string
  status: string
  feedback_submitted: boolean
}
export type Offer = {
  id: string
  candidate_id: string
  candidate_name: string
  title: string
  compensation: string
  employment_type: string
  joining_date: string
  status: string
  expires_at: string | null
  accepted_at: string | null
  created_at: string
  acceptance_url?: string
}
export type Task = {
  id: string
  candidate_id: string | null
  candidate_name: string | null
  assigned_to_id: string | null
  title: string
  due_at: string | null
  status: string
  created_at: string
}
export type TeamUser = {
  id: string
  name: string
  email: string
  role: string
  active: boolean
}
export type AuditEvent = {
  id: string
  actor_id: string | null
  entity_type: string
  entity_id: string
  action: string
  details: Record<string, unknown>
  created_at: string
}
export type Settings = {
  organization_id: string
  timezone: string
  careers_intro: string
  retention_days: number
  require_candidate_consent: boolean
}
export type MatchResult = {
  score: number
  methodology: string
  decision_note: string
  criteria: {
    skill: string
    category: string
    weight: number
    matched: boolean
    evidence_level: number
    evidence: string
  }[]
}
export type PublicJob = {
  id: string
  title: string
  location: string
  employment_type: string
  description: string
  organization_name: string
  requirements: string[]
}
export type PublicOffer = {
  candidate_name: string
  title: string
  compensation: string
  employment_type: string
  joining_date: string
  status: string
  expires_at: string | null
}
export type CandidatePortal = {
  candidate_name: string
  job_title: string
  application_status: string
  last_updated: string
  interviews: {
    title: string
    scheduled_for: string
    timezone: string
    status: string
  }[]
  offer_status: string | null
}
export type ResumeDocument = {
  id: string
  candidate_id: string
  original_name: string
  media_type: string
  size_bytes: number
  created_at: string
  extracted_skills: string[]
  extracted_experience: string
}
export type ResumeIntakeResult = {
  candidate: Candidate
  resume: ResumeDocument
  fields_needing_review: string[]
  matched_existing_candidate: boolean
  review_note: string
}
export type EmailTemplate = {
  id: string
  name: string
  subject: string
  body: string
  event_key: string
}
export type DraftMessage = {
  id: string
  recipient: string
  subject: string
  body: string
  status: string
  created_at: string
}

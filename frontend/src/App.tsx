import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Activity, ArrowLeft, ArrowUpRight, BriefcaseBusiness, CalendarDays, Check, ChevronDown, CircleHelp, ClipboardCheck, FileText, Filter, LayoutDashboard, LogOut, Mail, Plus, Search, Settings, ShieldCheck, SlidersHorizontal, Users, X } from 'lucide-react'
import './workspace.css'
import './responsive-nav.css'
import './features.css'
import './confirmation.css'
import './messaging.css'
import './timeline.css'
import './more-menu.css'
import './resume.css'
import './resume-intake.css'

type User = { id: string; email: string; name: string; role: string; organization_name: string }
type Candidate = { id: string; name: string; email: string | null; role_title: string; stage: string; experience: string; skills: string[]; current_ctc: string; expected_ctc: string; availability: string; created_at: string; score: number | null; job_id: string | null }
type Job = { id: string; title: string; location: string; employment_type: string; status: string; description: string; requirements: { skill: string; category: string; weight: number; min_evidence_level: number }[]; applications_count: number }
type Interview = { id: string; candidate_id: string; candidate_name: string; candidate_email: string | null; interviewer_id: string | null; title: string; scheduled_for: string; duration_minutes: number; timezone: string; meeting_method: string; location_or_link: string; status: string; feedback_submitted: boolean }
type Offer = { id: string; candidate_id: string; candidate_name: string; title: string; compensation: string; employment_type: string; joining_date: string; status: string; expires_at: string | null; accepted_at: string | null; created_at: string; acceptance_url?: string }
type Task = { id: string; candidate_id: string | null; candidate_name: string | null; assigned_to_id: string | null; title: string; due_at: string | null; status: string; created_at: string }
type TeamUser = { id: string; name: string; email: string; role: string; active: boolean }
type AuditEvent = { id: string; actor_id: string | null; entity_type: string; entity_id: string; action: string; details: Record<string, unknown>; created_at: string }
type Settings = { organization_id: string; timezone: string; careers_intro: string; retention_days: number; require_candidate_consent: boolean }
type MatchResult = { score: number; methodology: string; decision_note: string; criteria: { skill: string; category: string; weight: number; matched: boolean; evidence_level: number; evidence: string }[] }
type PublicJob = { id: string; title: string; location: string; employment_type: string; description: string; organization_name: string; requirements: string[] }
type PublicOffer = { candidate_name: string; title: string; compensation: string; employment_type: string; joining_date: string; status: string; expires_at: string | null }
type CandidatePortal = { candidate_name: string; job_title: string; application_status: string; last_updated: string; interviews: { title: string; scheduled_for: string; timezone: string; status: string }[]; offer_status: string | null }
type ResumeDocument = { id: string; candidate_id: string; original_name: string; media_type: string; size_bytes: number; created_at: string; extracted_skills: string[]; extracted_experience: string }
type ResumeIntakeResult = { candidate: Candidate; resume: ResumeDocument; fields_needing_review: string[]; matched_existing_candidate: boolean; review_note: string }
type EmailTemplate = { id: string; name: string; subject: string; body: string; event_key: string }
type DraftMessage = { id: string; recipient: string; subject: string; body: string; status: string; created_at: string }
type ApiError = { detail?: string | { msg: string }[] }
type View = 'overview' | 'candidates' | 'jobs' | 'interviews' | 'offers' | 'tasks' | 'team' | 'settings' | 'audit' | 'messages'

const apiUrl = import.meta.env.VITE_API_URL ?? '/api'
const stages = ['New', 'Applied', 'Resume Parsed', 'AI Screened', 'Recruiter Review', 'Screening', 'Telephone Discussion', 'Tech round 1', 'Tech round 2', 'Final Discussion', 'Offer Approval', 'Offer', 'Offer Sent', 'Offer Accepted', 'Joining Confirmed', 'Hired', 'Hold', 'Rejected', 'No Response', 'Candidate Withdrew', 'Offer Declined', 'Closed']
const navigation: { id: View; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard }, { id: 'candidates', label: 'Candidates', icon: Users },
  { id: 'jobs', label: 'Jobs & careers', icon: BriefcaseBusiness }, { id: 'interviews', label: 'Interviews', icon: CalendarDays },
  { id: 'offers', label: 'Offers', icon: FileText }, { id: 'tasks', label: 'My tasks', icon: ClipboardCheck },
]

async function api<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers } })
  if (!response.ok) {
    const error = await response.json().catch(() => ({})) as ApiError
    const detail = Array.isArray(error.detail) ? error.detail.map((issue) => issue.msg).join('; ') : error.detail
    throw new Error(detail ?? `Request failed (${response.status})`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

function errorText(value: unknown) { return value instanceof Error ? value.message : 'The request could not be completed' }
function formatDate(value: string | null) { return value ? new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : 'Not scheduled' }
function stageClass(value: string) { return `stage-pill stage-${value.toLowerCase().replaceAll(' ', '-')}` }
function initials(value: string) { return value.split(' ').map((part) => part[0]).join('').slice(0, 2).toUpperCase() }
function Field({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) { return <label className={wide ? 'wide-field' : ''}>{label}{children}</label> }

function App() {
  const initialPath = window.location.pathname
  const [token, setToken] = useState(() => sessionStorage.getItem('hireflowToken') ?? '')
  const [hydrating, setHydrating] = useState(() => Boolean(sessionStorage.getItem('hireflowToken')))
  const [user, setUser] = useState<User | null>(() => {
    try { return JSON.parse(sessionStorage.getItem('hireflowUser') ?? 'null') as User | null }
    catch { return null }
  })
  const [view, setView] = useState<View>('overview')
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [interviews, setInterviews] = useState<Interview[]>([])
  const [offers, setOffers] = useState<Offer[]>([])
  const [offerLinks, setOfferLinks] = useState<Record<string, string>>(() => {
    try { return JSON.parse(sessionStorage.getItem('hireflowOfferLinks') ?? '{}') as Record<string, string> }
    catch { return {} }
  })
  const [tasks, setTasks] = useState<Task[]>([])
  const [team, setTeam] = useState<TeamUser[]>([])
  const [audit, setAudit] = useState<AuditEvent[]>([])
  const [templates, setTemplates] = useState<EmailTemplate[]>([])
  const [outbox, setOutbox] = useState<DraftMessage[]>([])
  const [settings, setSettings] = useState<Settings | null>(null)
  const [selected, setSelected] = useState<Candidate | null>(null)
  const [candidateActivity, setCandidateActivity] = useState<AuditEvent[]>([])
  const [resumeDocuments, setResumeDocuments] = useState<ResumeDocument[]>([])
  const [uploadingResume, setUploadingResume] = useState(false)
  const [showResumeIntake, setShowResumeIntake] = useState(false)
  const [intakingResumes, setIntakingResumes] = useState(false)
  const [matchResult, setMatchResult] = useState<MatchResult | null>(null)
  const [publicJobs, setPublicJobs] = useState<PublicJob[]>([])
  const [publicOffer, setPublicOffer] = useState<PublicOffer | null>(null)
  const [search, setSearch] = useState('')
  const [stageFilter, setStageFilter] = useState('')
  const [sortBy, setSortBy] = useState('recent')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [modal, setModal] = useState<'candidate' | 'job' | 'screening' | 'interview' | 'feedback' | 'offer' | 'task' | 'team' | null>(null)
  const [modalCandidateId, setModalCandidateId] = useState('')
  const [showMobileMore, setShowMobileMore] = useState(false)
  const isCareers = initialPath === '/careers' || initialPath.startsWith('/careers/')
  const offerToken = initialPath.startsWith('/offer/') ? initialPath.split('/')[2] : ''
  const candidateToken = initialPath.startsWith('/candidate/') ? initialPath.split('/')[2] : ''
  const [candidatePortal, setCandidatePortal] = useState<CandidatePortal | null>(null)

  async function loadRecruiterData(activeToken = token) {
    try {
      const [candidateRows, jobRows, interviewRows, offerRows, taskRows] = await Promise.all([
        api<Candidate[]>('/candidates', activeToken), api<Job[]>('/jobs', activeToken), api<Interview[]>('/interviews', activeToken),
        api<Offer[]>('/offers', activeToken), api<Task[]>('/tasks', activeToken),
      ])
      setCandidates(candidateRows); setJobs(jobRows); setInterviews(interviewRows); setOffers(offerRows); setTasks(taskRows)
      setSelected((current) => current ? candidateRows.find((candidate) => candidate.id === current.id) ?? null : null)
      setError('')
    } catch (cause) { setError(errorText(cause)) }
  }

  useEffect(() => {
    let cancelled = false
    if (isCareers) {
      api<PublicJob[]>('/public/jobs', '').then((items) => { if (!cancelled) setPublicJobs(items) }).catch((cause) => { if (!cancelled) setError(errorText(cause)) })
    } else if (offerToken) {
      api<PublicOffer>(`/public/offers/${offerToken}`, '').then((item) => { if (!cancelled) setPublicOffer(item) }).catch((cause) => { if (!cancelled) setError(errorText(cause)) })
    } else if (candidateToken) {
      api<CandidatePortal>(`/public/candidates/${candidateToken}`, '').then((item) => { if (!cancelled) setCandidatePortal(item) }).catch((cause) => { if (!cancelled) setError(errorText(cause)) })
    } else if (token) {
      api<User>('/auth/me', token).then(async () => {
        if (cancelled) return
        await loadRecruiterData(token)
        const cachedUser = JSON.parse(sessionStorage.getItem('hireflowUser') ?? 'null') as User | null
        if (cachedUser?.role === 'admin' || cachedUser?.role === 'hiring_manager') {
          const [users, orgSettings, events, emailTemplates, messages] = await Promise.all([
            api<TeamUser[]>('/team/directory', token).catch(() => []), api<Settings>('/settings', token).catch(() => null), api<AuditEvent[]>('/audit-events', token).catch(() => []),
            api<EmailTemplate[]>('/communications/templates', token).catch(() => []), cachedUser.role === 'admin' ? api<DraftMessage[]>('/communications/outbox', token).catch(() => []) : Promise.resolve([]),
          ])
          if (!cancelled) { setTeam(users); setSettings(orgSettings); setAudit(events); setTemplates(emailTemplates); setOutbox(messages) }
        } else {
          const [directory, emailTemplates] = await Promise.all([api<TeamUser[]>('/team/directory', token).catch(() => []), api<EmailTemplate[]>('/communications/templates', token).catch(() => [])])
          if (!cancelled) { setTeam(directory); setTemplates(emailTemplates) }
        }
      }).catch(() => { sessionStorage.removeItem('hireflowToken'); sessionStorage.removeItem('hireflowUser'); if (!cancelled) window.location.reload() }).finally(() => { if (!cancelled) setHydrating(false) })
    }
    return () => { cancelled = true }
  }, [token, isCareers, offerToken, candidateToken])

  useEffect(() => {
    if (!user || !token) return
    const interval = window.setInterval(() => { if (document.visibilityState === 'visible') void loadRecruiterData(token) }, 10000)
    return () => window.clearInterval(interval)
  }, [user, token])

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget); setError(''); setLoading(true)
    try {
      const response = await fetch(`${apiUrl}/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: form.get('email'), password: form.get('password') }) })
      const body = await response.json()
      if (!response.ok) throw new Error(Array.isArray(body.detail) ? body.detail.map((issue: { msg: string }) => issue.msg).join('; ') : body.detail ?? 'Sign-in failed')
      sessionStorage.setItem('hireflowToken', body.access_token); sessionStorage.setItem('hireflowUser', JSON.stringify(body.user)); setToken(body.access_token); setUser(body.user)
      setHydrating(true)
    } catch (cause) { setError(errorText(cause)) } finally { setLoading(false) }
  }

  function signOut() { sessionStorage.removeItem('hireflowToken'); sessionStorage.removeItem('hireflowUser'); setToken(''); setUser(null); setCandidates([]); setSelected(null) }
  async function submitForm(event: FormEvent<HTMLFormElement>, endpoint: string, success: string, method = 'POST', transform?: (form: FormData) => unknown) {
    event.preventDefault(); const form = new FormData(event.currentTarget)
    try {
      const body = transform ? transform(form) : Object.fromEntries(form.entries())
      const response = await api<unknown>(endpoint, token, { method, body: JSON.stringify(body) })
      if (endpoint === '/offers' && response && typeof response === 'object' && 'acceptance_url' in response && 'id' in response) {
        const createdOffer = response as Offer
        const nextLinks = { ...offerLinks, [createdOffer.id]: createdOffer.acceptance_url ?? '' }
        setOfferLinks(nextLinks)
        sessionStorage.setItem('hireflowOfferLinks', JSON.stringify(nextLinks))
      }
      setModal(null); setNotice(success); await loadRecruiterData()
      if (user && (user.role === 'admin' || user.role === 'hiring_manager')) {
        const [users, events] = await Promise.all([api<TeamUser[]>('/users', token).catch(() => []), api<AuditEvent[]>('/audit-events', token).catch(() => [])]); setTeam(users); setAudit(events)
      }
    } catch (cause) { setError(errorText(cause)) }
  }

  async function updateStage(candidate: Candidate, stage: string) {
    try { const updated = await api<Candidate>(`/candidates/${candidate.id}`, token, { method: 'PATCH', body: JSON.stringify({ stage }) }); setCandidates((items) => items.map((item) => item.id === updated.id ? updated : item)); setSelected(updated); setNotice('Pipeline stage updated') }
    catch (cause) { setError(errorText(cause)) }
  }

  async function updateCandidateEmail(candidate: Candidate, emailValue: string) {
    const email = emailValue.trim() || null
    if (email === candidate.email) return
    try {
      const updated = await api<Candidate>(`/candidates/${candidate.id}`, token, { method: 'PATCH', body: JSON.stringify({ email }) })
      setCandidates((items) => items.map((item) => item.id === updated.id ? updated : item))
      setSelected(updated)
      setNotice(email ? 'Candidate contact email updated' : 'Candidate email cleared')
    } catch (cause) { setError(errorText(cause)) }
  }

  async function openCandidate(candidate: Candidate) {
    setSelected(candidate)
    const [activity, resumes] = await Promise.all([
      api<AuditEvent[]>(`/candidates/${candidate.id}/activity`, token).catch((cause) => { setError(errorText(cause)); return [] }),
      api<ResumeDocument[]>(`/candidates/${candidate.id}/resumes`, token).catch(() => []),
    ])
    setCandidateActivity(activity)
    setResumeDocuments(resumes)
  }

  async function uploadResume(candidate: Candidate, file?: File) {
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    setUploadingResume(true)
    try {
      const response = await fetch(`${apiUrl}/candidates/${candidate.id}/resumes`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail ?? `Resume upload failed (${response.status})`)
      setResumeDocuments((items) => [result as ResumeDocument, ...items])
      setNotice(`Resume scanned and stored encrypted. Extracted profile fields are unverified: ${(result.extracted_skills as string[]).join(', ') || 'no listed skills found'}.`)
      await loadRecruiterData()
    } catch (cause) { setError(errorText(cause)) }
    finally { setUploadingResume(false) }
  }

  async function intakeResumes(files: File[], jobId: string, roleTitle: string) {
    if (!files.length) return
    setIntakingResumes(true)
    const imported: ResumeIntakeResult[] = []
    const failures: string[] = []
    try {
      for (const file of files) {
        const form = new FormData()
        form.append('file', file)
        if (jobId) form.append('job_id', jobId)
        if (roleTitle) form.append('role_title', roleTitle)
        try {
          const response = await fetch(`${apiUrl}/resume-intake`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form })
          const result = await response.json()
          if (!response.ok) throw new Error(result.detail ?? `Resume import failed (${response.status})`)
          imported.push(result as ResumeIntakeResult)
        } catch (cause) { failures.push(`${file.name}: ${errorText(cause)}`) }
      }
      if (imported.length) {
        await loadRecruiterData()
        const newProfiles = imported.filter((item) => !item.matched_existing_candidate).length
        const reviewCount = imported.reduce((sum, item) => sum + item.fields_needing_review.length, 0)
        setNotice(`Imported ${imported.length} resume${imported.length === 1 ? '' : 's'}; ${newProfiles} new profile${newProfiles === 1 ? '' : 's'} added. ${reviewCount} field${reviewCount === 1 ? '' : 's'} need review.`)
        setView('candidates')
      }
      if (failures.length) setError(failures.join(' | '))
      if (imported.length) setShowResumeIntake(false)
    } finally { setIntakingResumes(false) }
  }

  async function removeCandidate(candidate: Candidate) {
    if (!window.confirm(`Remove ${candidate.name} and their recruitment history?`)) return
    try { await api<void>(`/candidates/${candidate.id}`, token, { method: 'DELETE' }); setCandidates((items) => items.filter((item) => item.id !== candidate.id)); setSelected(null); setNotice('Candidate removed') }
    catch (cause) { setError(errorText(cause)) }
  }

  async function calculateMatch(candidate: Candidate) {
    const matchingJob = jobs.find((job) => job.id === candidate.job_id) ?? jobs.find((job) => job.title === candidate.role_title)
    if (!matchingJob) { setError('Create a job with structured requirements before calculating a match'); return }
    try { const result = await api<MatchResult>(`/candidates/${candidate.id}/match?job_id=${matchingJob.id}`, token, { method: 'POST' }); setMatchResult(result); await loadRecruiterData() }
    catch (cause) { setError(errorText(cause)) }
  }

  async function publishJob(job: Job, status: 'published' | 'closed') {
    try { await api<Job>(`/jobs/${job.id}/status?status_value=${status}`, token, { method: 'PATCH' }); setNotice(status === 'published' ? 'Job published to the public careers page' : 'Job closed'); await loadRecruiterData() }
    catch (cause) { setError(errorText(cause)) }
  }

  async function approveOffer(offer: Offer) {
    try { await api(`/offers/${offer.id}/approve`, token, { method: 'POST' }); setNotice('Offer approved. Candidate acceptance link is available to share. No email has been sent.'); await loadRecruiterData() }
    catch (cause) { setError(errorText(cause)) }
  }

  async function updateTask(task: Task) {
    try { await api(`/tasks/${task.id}`, token, { method: 'PATCH', body: JSON.stringify({ status: task.status === 'done' ? 'open' : 'done' }) }); await loadRecruiterData() }
    catch (cause) { setError(errorText(cause)) }
  }

  async function createEmailTemplate(payload: Omit<EmailTemplate, 'id'>, templateId?: string) {
    try {
      const saved = await api<EmailTemplate>(templateId ? `/communications/templates/${templateId}` : '/communications/templates', token, { method: templateId ? 'PUT' : 'POST', body: JSON.stringify(payload) })
      setTemplates((items) => templateId ? items.map((item) => item.id === templateId ? saved : item) : [...items, saved])
      setNotice('Email template saved. Delivery remains disabled until a provider is configured.')
    }
    catch (cause) { setError(errorText(cause)) }
  }

  async function createMessageDraft(payload: { template_id: string; candidate_id: string; subject?: string; body?: string }) {
    try { const draft = await api<DraftMessage>('/communications/drafts', token, { method: 'POST', body: JSON.stringify(payload) }); setOutbox((items) => [draft, ...items]); setNotice('Message draft saved. It has not been sent.') }
    catch (cause) { setError(errorText(cause)) }
  }

  async function acceptOffer(decision: 'accept' | 'decline') {
    try { const response = await api<{ status: string }>(`/public/offers/${offerToken}/decision?decision=${decision}`, '', { method: 'POST' }); setNotice(`Offer ${response.status}`); setPublicOffer((current) => current ? { ...current, status: response.status } : null) }
    catch (cause) { setError(errorText(cause)) }
  }

  const visibleCandidates = candidates.filter((candidate) => (!stageFilter || candidate.stage === stageFilter) && (!search || `${candidate.name} ${candidate.email} ${candidate.role_title} ${candidate.skills.join(' ')}`.toLowerCase().includes(search.toLowerCase())))
    .sort((a, b) => sortBy === 'name' ? a.name.localeCompare(b.name) : sortBy === 'score' ? (b.score ?? -1) - (a.score ?? -1) : Date.parse(b.created_at) - Date.parse(a.created_at))
  const activeCount = candidates.filter((candidate) => !['Hired', 'Rejected', 'Closed', 'Candidate Withdrew'].includes(candidate.stage)).length
  const stageCounts = ['Applied', 'Recruiter Review', 'Screening', 'Tech round 1', 'Tech round 2', 'Offer Approval', 'Offer Sent', 'Hired'].map((stage) => ({ stage, count: candidates.filter((candidate) => candidate.stage === stage).length }))
  const canRecruit = user?.role === 'admin' || user?.role === 'recruiter'
  const canAdminister = user?.role === 'admin'

  if (isCareers) return <main className="public-shell"><header className="public-header"><a className="brand-lockup" href="/careers"><span className="brand-mark">h</span><span>hireflow<span className="brand-period">.</span></span></a><span>Careers</span></header><div className="public-content"><p className="eyebrow">OPEN OPPORTUNITIES</p><h1>Find your next role.</h1><p className="heading-copy">Explore current openings and apply directly to the hiring team.</p>{error && <div className="alert error-alert">{error}</div>}{notice && <div className="alert success-alert"><Check size={16} />{notice}</div>}<div className="public-job-list">{publicJobs.map((job) => <article className="public-job" key={job.id}><div><h2>{job.title}</h2><p>{job.organization_name} · {job.location || 'Location flexible'} · {job.employment_type}</p><p className="public-description">{job.description}</p><div className="skill-list">{job.requirements.map((skill) => <span className="skill-chip" key={skill}>{skill}</span>)}</div></div><button className="button primary" onClick={() => { window.history.pushState({}, '', `/careers/apply/${job.id}`); window.location.reload() }}>Apply<ArrowUpRight size={16} /></button></article>)}{!publicJobs.length && <p className="empty-state">There are no published openings right now.</p>}</div></div>{initialPath.startsWith('/careers/apply/') && <PublicApplication jobId={initialPath.split('/')[3]} jobs={publicJobs} onDone={(message) => setNotice(message)} onError={setError} />}</main>

  if (candidateToken) return <main className="login-shell"><section className="offer-accept-panel"><div className="brand-lockup"><span className="brand-mark">h</span><span>hireflow<span className="brand-period">.</span></span></div>{error ? <div className="alert error-alert">{error}</div> : candidatePortal ? <><p className="eyebrow">APPLICATION STATUS</p><h1>{candidatePortal.job_title}</h1><p>Candidate: {candidatePortal.candidate_name}</p><div className="offer-summary"><span>Current status</span><b>{candidatePortal.application_status}</b><span>Last updated</span><b>{formatDate(candidatePortal.last_updated)}</b>{candidatePortal.offer_status && <><span>Offer</span><b>{candidatePortal.offer_status}</b></>}</div><h2 className="portal-subheading">Interview schedule</h2>{candidatePortal.interviews.length ? candidatePortal.interviews.map((item, index) => <p key={`${item.title}-${index}`}>{item.title} · {new Date(item.scheduled_for).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short', timeZone: item.timezone })} · {item.status}</p>) : <p>No interviews scheduled.</p>}<button className="button danger-outline" onClick={async () => { try { await api(`/public/candidates/${candidateToken}/withdraw`, '', { method: 'POST' }); setNotice('Application withdrawn'); setCandidatePortal({ ...candidatePortal, application_status: 'Candidate Withdrew' }) } catch (cause) { setError(errorText(cause)) } }}>Withdraw application</button></> : <p>Loading application status…</p>}{notice && <div className="alert success-alert">{notice}</div>}</section></main>

  if (offerToken) return <main className="login-shell"><section className="offer-accept-panel"><div className="brand-lockup"><span className="brand-mark">h</span><span>hireflow<span className="brand-period">.</span></span></div>{error ? <div className="alert error-alert">{error}</div> : publicOffer ? <><p className="eyebrow">OFFER LETTER</p><h1>{publicOffer.title}</h1><p>Prepared for {publicOffer.candidate_name}</p><div className="offer-summary"><span>Compensation</span><b>{publicOffer.compensation}</b><span>Employment type</span><b>{publicOffer.employment_type}</b><span>Joining date</span><b>{publicOffer.joining_date || 'To be agreed'}</b><span>Status</span><b>{publicOffer.status}</b></div>{['approved', 'sent'].includes(publicOffer.status) && <div className="drawer-actions"><button className="button primary" onClick={() => void acceptOffer('accept')}>Accept offer</button><button className="button outline" onClick={() => void acceptOffer('decline')}>Decline</button></div>}</> : <p>Loading offer…</p>}{notice && <div className="alert success-alert">{notice}</div>}</section></main>

  if (hydrating) return <main className="login-shell"><div className="login-panel"><div className="brand-lockup"><span className="brand-mark">h</span><span>hireflow<span className="brand-period">.</span></span></div><p className="eyebrow">RECRUITER WORKSPACE</p><h1>Loading your pipeline.</h1><p className="login-copy">Checking your organisation access and loading the latest records.</p></div></main>
  if (!user) return <main className="login-shell"><form className="login-panel" onSubmit={signIn}><div className="brand-lockup"><span className="brand-mark">h</span><span>hireflow<span className="brand-period">.</span></span></div><p className="eyebrow">RECRUITER WORKSPACE</p><h1>Hiring, in motion.</h1><p className="login-copy">Sign in to your organisation's hiring pipeline.</p><label>Email address<input name="email" type="email" placeholder="you@company.com" required autoComplete="username" /></label><label>Password<input name="password" type="password" required autoComplete="current-password" /></label>{error && <div className="alert error-alert">{error}</div>}<button className="button primary full-button" disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}<ArrowUpRight size={17} /></button><p className="secure-caption">Organisation accounts are provisioned by your administrator.</p></form></main>

  const heading = navigation.find((item) => item.id === view)?.label ?? (view === 'team' ? 'Team & access' : view === 'settings' ? 'Organisation settings' : view === 'audit' ? 'Audit history' : 'Messages & templates')
  const viewChange = (next: View) => { setView(next); setSelected(null); setMatchResult(null); setError(''); setNotice('') }

  return <div className="app-shell">
    <aside className="sidebar"><a className="brand-lockup" href="/"><span className="brand-mark">h</span><span>hireflow<span className="brand-period">.</span></span></a><div className="workspace-label">WORKSPACE</div><nav className="side-nav">{navigation.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-item ${view === id ? 'active' : ''}`} onClick={() => viewChange(id)}><Icon size={18} />{label}{id === 'candidates' && <span className="nav-count">{candidates.length}</span>}</button>)}<button className={`nav-item mobile-more ${showMobileMore ? 'active' : ''}`} onClick={() => setShowMobileMore((value) => !value)}><Settings size={18} />More</button></nav>{showMobileMore && <div className="mobile-more-menu">{(canAdminister || user.role === 'hiring_manager') && <><button onClick={() => { viewChange('team'); setShowMobileMore(false) }}><Users size={16} />Team & access</button><button onClick={() => { viewChange('settings'); setShowMobileMore(false) }}><Settings size={16} />Settings</button><button onClick={() => { viewChange('audit'); setShowMobileMore(false) }}><ShieldCheck size={16} />Audit log</button></>}<button onClick={() => { viewChange('messages'); setShowMobileMore(false) }}><Mail size={16} />Messages</button><button onClick={signOut}><LogOut size={16} />Sign out</button></div>}<div className="sidebar-foot">{(canAdminister || user.role === 'hiring_manager') && <><button className={`nav-item ${view === 'team' ? 'active' : ''}`} onClick={() => viewChange('team')}><Users size={18} />Team & access</button><button className={`nav-item ${view === 'settings' ? 'active' : ''}`} onClick={() => viewChange('settings')}><Settings size={18} />Settings</button><button className={`nav-item ${view === 'audit' ? 'active' : ''}`} onClick={() => viewChange('audit')}><ShieldCheck size={18} />Audit log</button></>}<button className={`nav-item ${view === 'messages' ? 'active' : ''}`} onClick={() => viewChange('messages')}><Mail size={18} />Messages</button><div className="profile-row"><span className="profile-avatar">{initials(user.name)}</span><span className="profile-copy"><b>{user.name}</b><small>{user.role} · {user.organization_name}</small></span><button className="icon-button" title="Sign out" onClick={signOut}><LogOut size={16} /></button></div></div></aside>
    <main className="main-area"><header className="topbar"><div className="mobile-brand"><span className="brand-mark">h</span>hireflow</div><div className="breadcrumb">Workspace <span>/</span> {heading}</div><div className="top-actions"><button className="icon-button" title="Help"><CircleHelp size={18} /></button><span className="top-divider" /><span className="top-org">{user.organization_name}</span><ChevronDown size={15} /></div></header><div className="page-content">
      <section className="page-heading"><div><p className="eyebrow">{user.organization_name.toUpperCase()}</p><h1>{view === 'overview' ? `Good morning, ${user.name.split(' ')[0]}.` : heading}</h1><p className="heading-copy">{view === 'overview' ? 'Your recruitment pipeline, priority actions and upcoming decisions.' : view === 'candidates' ? 'Candidate records, evidence, stage history and recruiter decisions.' : `Manage ${heading.toLowerCase()} for your organisation.`}</p></div>{canRecruit && <button className="button primary" onClick={() => setModal(view === 'jobs' ? 'job' : view === 'interviews' ? 'interview' : view === 'offers' ? 'offer' : view === 'tasks' ? 'task' : 'candidate')}><Plus size={17} />{view === 'jobs' ? 'Create job' : view === 'interviews' ? 'Schedule interview' : view === 'offers' ? 'Prepare offer' : view === 'tasks' ? 'Add task' : 'Add candidate'}</button>}</section>
      {error && <div className="alert error-alert">{error}<button className="icon-button" onClick={() => setError('')}><X size={15} /></button></div>}{notice && <div className="alert success-alert"><Check size={16} />{notice}<button className="icon-button" onClick={() => setNotice('')}><X size={15} /></button></div>}
      {view === 'candidates' && canRecruit && <div className="resume-first-banner"><div><b>Skip manual candidate entry</b><span>Upload one or more resumes to extract profiles and add them to the pipeline.</span></div><button className="button primary" onClick={() => setShowResumeIntake(true)}><Plus size={16} />Import resumes</button></div>}
      {view === 'overview' && <><section className="metric-grid"><article className="metric"><div className="metric-label">Active candidates <Users size={16} /></div><strong>{activeCount}</strong><small>in the current pipeline</small></article><article className="metric"><div className="metric-label">Published jobs <BriefcaseBusiness size={16} /></div><strong>{jobs.filter((job) => job.status === 'published').length}</strong><small>receiving applications</small></article><article className="metric"><div className="metric-label">Upcoming interviews <CalendarDays size={16} /></div><strong>{interviews.filter((item) => item.status === 'scheduled').length}</strong><small>stored interview schedule</small></article><article className="metric"><div className="metric-label">Open tasks <Activity size={16} /></div><strong>{tasks.filter((task) => task.status === 'open').length}</strong><small>recruiter follow-ups</small></article></section><section className="pipeline-panel"><div className="section-title"><div><h2>Hiring pipeline</h2><p>Candidate distribution across configured stages</p></div><span className="live-indicator"><i /> REFRESHES EVERY 10 SEC</span></div><div className="pipeline-track">{stageCounts.map(({ stage, count }) => <button key={stage} className="pipeline-stage" onClick={() => { setStageFilter(stage); viewChange('candidates') }}><span className="stage-name">{stage}</span><strong>{count}</strong><span className="stage-meter"><i style={{ width: `${candidates.length ? Math.max(count / candidates.length * 100, count ? 8 : 0) : 0}%` }} /></span></button>)}</div></section><section className="two-panel-grid"><div className="pipeline-panel"><div className="section-title"><div><h2>Priority actions</h2><p>Follow-ups and incomplete steps</p></div><button className="action-link" onClick={() => viewChange('tasks')}>View tasks</button></div><TaskList tasks={tasks.filter((task) => task.status === 'open').slice(0, 5)} onToggle={updateTask} /></div><div className="pipeline-panel"><div className="section-title"><div><h2>Next interviews</h2><p>Scheduled in the workspace</p></div><button className="action-link" onClick={() => viewChange('interviews')}>View schedule</button></div><InterviewList interviews={interviews.filter((item) => item.status === 'scheduled').slice(0, 5)} onFeedback={(item) => { setModalCandidateId(item.id); setModal('feedback') }} /></div></section></>}
      {view === 'candidates' && <CandidateView candidates={visibleCandidates} jobs={jobs} search={search} stageFilter={stageFilter} sortBy={sortBy} onSearch={setSearch} onStageFilter={setStageFilter} onSort={setSortBy} onOpen={(candidate) => void openCandidate(candidate)} />}
      {view === 'jobs' && <JobView jobs={jobs} onCreate={() => setModal('job')} onStatus={publishJob} onCareers={() => window.open('/careers', '_blank', 'noopener')} />}
      {view === 'interviews' && <InterviewList interviews={interviews} onFeedback={(item) => { setModalCandidateId(item.id); setModal('feedback') }} />}
      {view === 'offers' && <OfferList offers={offers.map((offer) => ({ ...offer, acceptance_url: offerLinks[offer.id] }))} canApprove={user.role === 'admin' || user.role === 'hiring_manager'} onApprove={approveOffer} onCreate={() => setModal('offer')} onCopy={(offer) => { const url = `${window.location.origin}${offer.acceptance_url ?? ''}`; void navigator.clipboard?.writeText(url); setNotice('Offer link copied. Share it through your configured communication channel.') }} />}
      {view === 'tasks' && <TaskList tasks={tasks} onToggle={updateTask} />}
      {view === 'team' && <TeamView team={team} canManage={canAdminister} onInvite={() => setModal('team')} />}
      {view === 'settings' && <SettingsView settings={settings} canEdit={canAdminister} onSave={(event) => void submitForm(event, '/settings', 'Organisation settings saved', 'PUT', (form) => ({ timezone: form.get('timezone'), careers_intro: form.get('careers_intro'), retention_days: Number(form.get('retention_days')), require_candidate_consent: form.get('require_candidate_consent') === 'on' }))} />}
      {view === 'audit' && <AuditView events={audit} />}
      {view === 'messages' && <MessagesView templates={templates} candidates={candidates} outbox={outbox} canCreate={canRecruit} onSaveTemplate={createEmailTemplate} onCreateDraft={createMessageDraft} />}
    </div></main>
    {selected && <div className="drawer-backdrop" onClick={(event) => { if (event.target === event.currentTarget) { setSelected(null); setMatchResult(null) } }}><aside className="candidate-drawer"><div className="drawer-header"><div><p className="eyebrow">CANDIDATE PROFILE</p><h2>{selected.name}</h2><p>{selected.role_title}</p></div><button className="icon-button" onClick={() => { setSelected(null); setMatchResult(null) }}><X size={19} /></button></div><div className="drawer-body"><CandidateEmail candidate={selected} editable={canRecruit} onSave={(value) => void updateCandidateEmail(selected, value)} /><div className="detail-columns"><Detail label="Experience">{selected.experience || 'Not collected'}</Detail><Detail label="Availability">{selected.availability || 'Not collected'}</Detail></div><Detail label="Skills"><div className="skill-list">{selected.skills.map((skill) => <span className="skill-chip" key={skill}>{skill}</span>)}</div></Detail>{canRecruit && <div className="detail-columns"><Detail label="Current CTC">{selected.current_ctc || 'Not collected'}</Detail><Detail label="Expected CTC">{selected.expected_ctc || 'Not collected'}</Detail></div>}{canRecruit && <div className="resume-panel"><div><b>Resume</b><small>PDF/DOCX · malware scanned · encrypted at rest</small></div><label className={`button outline resume-upload ${uploadingResume ? 'disabled-button' : ''}`}>{uploadingResume ? 'Scanning…' : 'Upload resume'}<input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={uploadingResume} onChange={(event) => void uploadResume(selected, event.target.files?.[0])} /></label>{resumeDocuments.map((resume) => <div className="resume-item" key={resume.id}><FileText size={15} /><span>{resume.original_name}<small>{Math.ceil(resume.size_bytes / 1024)} KB · parsed fields unverified</small></span></div>)}</div>}{canRecruit ? <label className="stage-editor">Pipeline stage<select value={selected.stage} onChange={(event) => void updateStage(selected, event.target.value)}>{stages.map((stage) => <option key={stage}>{stage}</option>)}</select></label> : <div className="detail-block"><span className="detail-label">PIPELINE STAGE</span><span className={stageClass(selected.stage)}>{selected.stage}</span></div>}<div className="drawer-actions wrap-actions">{canRecruit && <button className="button primary" onClick={() => { setModalCandidateId(selected.id); setModal('screening') }}><Activity size={15} />Telephone screen</button>}{['admin', 'recruiter', 'hiring_manager'].includes(user.role) && <button className="button outline" onClick={() => setModal('interview')}><CalendarDays size={15} />Interview</button>}{canRecruit && <button className="button outline" onClick={() => setModal('offer')}><FileText size={15} />Offer</button>}</div>{canRecruit && jobs.length > 0 && <div className="match-actions"><label className="stage-editor">Compare with role<select id="matchJobId" defaultValue={selected.job_id ?? ''}><option value="">Choose a role</option>{jobs.map((job) => <option value={job.id} key={job.id}>{job.title}</option>)}</select></label><button className="button outline" onClick={() => { const target = jobs.find((job) => job.id === (document.getElementById('matchJobId') as HTMLSelectElement)?.value); if (target) void calculateMatch({ ...selected, job_id: target.id }); else void calculateMatch(selected) }}>Calculate profile match</button></div>}{matchResult && canRecruit && <div className="match-result"><b>{matchResult.score}% profile match</b><p>{matchResult.decision_note}</p>{matchResult.criteria.map((item) => <div className="match-criterion" key={item.skill}><span>{item.matched ? '✓' : '−'} {item.skill} · {item.category}</span><small>{item.evidence}</small></div>)}</div>}<h3>Activity history</h3><div className="candidate-timeline">{candidateActivity.map((event) => <article className="activity-item" key={event.id}><b>{event.action.replaceAll('_', ' ')}</b><small>{formatDate(event.created_at)}</small><span>{event.entity_type}{Object.keys(event.details).length ? ` · ${JSON.stringify(event.details)}` : ''}</span></article>)}{!candidateActivity.length && <p className="drawer-note">No recorded activity yet.</p>}</div>{canRecruit && <button className="button danger-outline" onClick={() => void removeCandidate(selected)}>Remove candidate</button>}</div></aside></div>}
    {modal && <WorkflowModal kind={modal} candidates={candidates} jobs={jobs} team={team} selectedCandidateId={modalCandidateId || selected?.id || ''} onClose={() => setModal(null)} onSubmit={(event, endpoint, success, method, transform) => void submitForm(event, endpoint, success, method, transform)} />}
    {showResumeIntake && <ResumeIntakeModal jobs={jobs} loading={intakingResumes} onClose={() => setShowResumeIntake(false)} onImport={intakeResumes} />}
  </div>
}

function Detail({ label, children }: { label: string; children: ReactNode }) { return <div className="detail-block"><span className="detail-label">{label.toUpperCase()}</span><b>{children}</b></div> }

function CandidateEmail({ candidate, editable, onSave }: { candidate: Candidate; editable: boolean; onSave: (value: string) => void }) {
  if (!editable) return <Detail label="Email">{candidate.email || 'Not provided'}</Detail>
  return <label className="email-review-field"><span className="detail-label">CONTACT EMAIL {candidate.email ? '' : '· NEEDS REVIEW'}</span><input key={candidate.id} aria-label="Candidate email" type="email" defaultValue={candidate.email ?? ''} placeholder="Not found in resume" onBlur={(event) => onSave(event.currentTarget.value)} /></label>
}

function ResumeIntakeModal({ jobs, loading, onClose, onImport }: { jobs: Job[]; loading: boolean; onClose: () => void; onImport: (files: File[], jobId: string, roleTitle: string) => void }) {
  const [files, setFiles] = useState<File[]>([])
  const [jobId, setJobId] = useState(jobs.find((job) => job.status === 'published')?.id ?? '')
  const [roleTitle, setRoleTitle] = useState('')
  const selectedJob = jobs.find((job) => job.id === jobId)
  return <div className="modal-backdrop" onClick={(event) => { if (event.target === event.currentTarget) onClose() }}><section className="form-modal"><div className="modal-heading"><div><p className="eyebrow">RESUME INTAKE</p><h2>Import candidates from resumes</h2></div><button className="icon-button" onClick={onClose}><X size={19} /></button></div><p className="resume-intake-copy">Select several PDF or DOCX resumes. HireFlow will scan and parse each file, create or match candidate profiles, and show missing fields for review.</p><div className="intake-drop"><FileText size={22} /><b>{files.length ? `${files.length} resume${files.length === 1 ? '' : 's'} selected` : 'Choose resumes to import'}</b><small>{files.map((file) => file.name).join(' · ') || 'PDF or DOCX · up to 10 MB per file'}</small><label className="button outline">Browse files<input type="file" multiple accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} /></label></div><div className="form-grid intake-fields"><Field label="Apply to role"><select value={jobId} onChange={(event) => setJobId(event.target.value)}><option value="">Select a role or enter a title</option>{jobs.map((job) => <option value={job.id} key={job.id}>{job.title} · {job.status}</option>)}</select></Field>{!selectedJob && <Field label="Role title"><input value={roleTitle} onChange={(event) => setRoleTitle(event.target.value)} placeholder="e.g. Data Engineer" /></Field>}</div><p className="form-disclaimer">Candidate records are created only after malware scanning and encrypted storage succeed. Resume text and extracted fields are unverified. Missing email addresses can be reviewed in each profile.</p><div className="modal-actions"><button className="button outline" onClick={onClose}>Cancel</button><button className="button primary" disabled={loading || !files.length || (!jobId && !roleTitle.trim())} onClick={() => onImport(files, jobId, selectedJob?.title ?? roleTitle.trim())}>{loading ? 'Scanning and importing…' : `Import ${files.length || ''} resume${files.length === 1 ? '' : 's'}`}</button></div></section></div>
}

function CandidateView({ candidates, jobs, search, stageFilter, sortBy, onSearch, onStageFilter, onSort, onOpen }: { candidates: Candidate[]; jobs: Job[]; search: string; stageFilter: string; sortBy: string; onSearch: (value: string) => void; onStageFilter: (value: string) => void; onSort: (value: string) => void; onOpen: (candidate: Candidate) => void }) {
  return <section className="candidate-section"><div className="table-toolbar"><label className="search-field"><Search size={17} /><input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Search candidate, skill, role" /></label><label className="select-field"><Filter size={15} /><select value={stageFilter} onChange={(event) => onStageFilter(event.target.value)}><option value="">All stages</option>{stages.map((stage) => <option key={stage}>{stage}</option>)}</select></label><label className="select-field"><SlidersHorizontal size={15} /><select value={sortBy} onChange={(event) => onSort(event.target.value)}><option value="recent">Recently added</option><option value="score">Match score</option><option value="name">Name A–Z</option></select></label></div><div className="table-scroll"><table><thead><tr><th>Candidate</th><th>Role</th><th>Experience</th><th>Skills</th><th>Availability</th><th>Match</th><th>Stage</th></tr></thead><tbody>{candidates.map((candidate) => <tr key={candidate.id} onClick={() => onOpen(candidate)}><td><span className="candidate-cell"><span className="candidate-avatar">{initials(candidate.name)}</span><span><b>{candidate.name}</b><small>{candidate.email}</small></span></span></td><td>{candidate.role_title}</td><td>{candidate.experience || '—'}</td><td><div className="skill-list">{candidate.skills.slice(0, 3).map((skill) => <span className="skill-chip" key={skill}>{skill}</span>)}</div></td><td>{candidate.availability || '—'}</td><td>{candidate.score == null ? <span className="secondary-text">Not scored</span> : `${candidate.score}%`}</td><td><span className={stageClass(candidate.stage)}>{candidate.stage}</span></td></tr>)}{!candidates.length && <tr><td className="empty-state" colSpan={7}>No candidates match. Add candidates manually or publish a role to collect applications.</td></tr>}</tbody></table></div><div className="table-footer"><span>Showing {candidates.length} candidates</span><span>Match evidence remains unverified until resume parsing is configured.</span></div>{jobs.length === 0 && <p className="form-disclaimer">Create a role with must-have and nice-to-have skills to enable profile comparison.</p>}</section>
}

function JobView({ jobs, onCreate, onStatus, onCareers }: { jobs: Job[]; onCreate: () => void; onStatus: (job: Job, status: 'published' | 'closed') => void; onCareers: () => void }) {
  return <><div className="section-title page-section-title"><div><h2>Open roles and requisitions</h2><p>Define weighted skills, publish openings and collect consent-based applications.</p></div><button className="button outline" onClick={onCareers}><ArrowUpRight size={15} />Preview careers</button></div><div className="job-grid">{jobs.map((job) => <article className="job-card" key={job.id}><div className="job-card-top"><span className={`stage-pill stage-${job.status}`}>{job.status}</span><span>{job.applications_count} applications</span></div><h2>{job.title}</h2><p>{job.location || 'Location flexible'} · {job.employment_type}</p><p className="job-description">{job.description || 'No description provided.'}</p><div className="job-requirements">{job.requirements.map((item) => <span className="skill-chip" key={`${item.skill}-${item.category}`}>{item.skill} · {item.category.replaceAll('_', ' ')}</span>)}</div><div className="card-actions">{job.status === 'draft' && <button className="button primary" onClick={() => onStatus(job, 'published')}>Publish role</button>}{job.status === 'published' && <button className="button outline" onClick={() => onStatus(job, 'closed')}>Close role</button>}{job.status === 'closed' && <button className="button outline" onClick={() => onStatus(job, 'published')}>Reopen role</button>}<button className="button outline" onClick={() => void navigator.clipboard?.writeText(`${window.location.origin}/careers/apply/${job.id}`)}>Copy application link</button></div></article>)}{!jobs.length && <div className="empty-panel"><BriefcaseBusiness size={22} /><b>No jobs created yet</b><p>Create a role and define its requirements before publishing to the careers page.</p><button className="button primary" onClick={onCreate}><Plus size={15} />Create the first role</button></div>}</div></>
}

function InterviewList({ interviews, onFeedback }: { interviews: Interview[]; onFeedback: (interview: Interview) => void }) {
  return <section className="candidate-section"><div className="section-title candidate-title"><div><h2>Interview schedule</h2><p>Schedule entries are stored. Calendar events, meeting links and invitations require a configured provider.</p></div></div><div className="table-scroll"><table><thead><tr><th>Candidate</th><th>Interview</th><th>Time</th><th>Method</th><th>Interviewer</th><th>Status</th><th>Feedback</th></tr></thead><tbody>{interviews.map((item) => <tr key={item.id}><td>{item.candidate_name}<small className="table-subline">{item.candidate_email}</small></td><td>{item.title}</td><td>{new Date(item.scheduled_for).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short', timeZone: item.timezone })}<small className="table-subline">{item.timezone} · {item.duration_minutes} min</small></td><td>{item.meeting_method}{item.location_or_link && <small className="table-subline">{item.location_or_link}</small>}</td><td>{item.interviewer_id ? 'Assigned teammate' : 'Unassigned'}</td><td><span className={stageClass(item.status)}>{item.status}</span></td><td>{item.feedback_submitted ? <span className="status-text">Submitted</span> : <button className="action-link" onClick={() => onFeedback(item)}>Add feedback</button>}</td></tr>)}{!interviews.length && <tr><td colSpan={7} className="empty-state">No interviews scheduled.</td></tr>}</tbody></table></div></section>
}

function OfferList({ offers, canApprove, onApprove, onCreate, onCopy }: { offers: Offer[]; canApprove: boolean; onApprove: (offer: Offer) => void; onCreate: () => void; onCopy: (offer: Offer) => void }) {
  return <section className="candidate-section"><div className="section-title candidate-title"><div><h2>Offer workflow</h2><p>Draft, approve and share candidate acceptance links. Email delivery is not configured.</p></div><button className="button outline" onClick={onCreate}><Plus size={15} />Prepare offer</button></div><div className="table-scroll"><table><thead><tr><th>Candidate</th><th>Role</th><th>Compensation</th><th>Joining date</th><th>Status</th><th>Approval</th><th>Candidate</th></tr></thead><tbody>{offers.map((offer) => <tr key={offer.id}><td>{offer.candidate_name}</td><td>{offer.title} · {offer.employment_type}</td><td>{offer.compensation}</td><td>{offer.joining_date || 'To be agreed'}</td><td><span className={stageClass(offer.status)}>{offer.status}</span></td><td>{offer.status === 'draft' && canApprove ? <button className="action-link" onClick={() => onApprove(offer)}>Approve</button> : offer.status === 'draft' ? 'Awaiting approver' : 'Recorded'}</td><td>{['approved', 'sent'].includes(offer.status) ? <button className="action-link" onClick={() => onCopy(offer)}>Copy acceptance link</button> : offer.status === 'accepted' ? formatDate(offer.accepted_at) : '—'}</td></tr>)}{!offers.length && <tr><td colSpan={7} className="empty-state">No offers created.</td></tr>}</tbody></table></div></section>
}

function TaskList({ tasks, onToggle }: { tasks: Task[]; onToggle: (task: Task) => void }) {
  return <div className="task-list">{tasks.map((task) => <article className={`task-row ${task.status === 'done' ? 'task-done' : ''}`} key={task.id}><button className="task-check" title={task.status === 'done' ? 'Reopen task' : 'Complete task'} onClick={() => onToggle(task)}>{task.status === 'done' && <Check size={14} />}</button><div><b>{task.title}</b><small>{task.candidate_name ?? 'Organisation task'} · {formatDate(task.due_at)}</small></div><span className={stageClass(task.status)}>{task.status}</span></article>)}{!tasks.length && <div className="empty-panel compact-empty"><ClipboardCheck size={22} /><b>No follow-up tasks</b><p>Add a recruiter reminder and due date.</p></div>}</div>
}

function TeamView({ team, canManage, onInvite }: { team: TeamUser[]; canManage: boolean; onInvite: () => void }) {
  return <section className="candidate-section"><div className="section-title candidate-title"><div><h2>Organisation members</h2><p>Recruiters, hiring managers and interviewers. User provisioning is admin-controlled.</p></div>{canManage && <button className="button outline" onClick={onInvite}><Plus size={15} />Add teammate</button>}</div><div className="table-scroll"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Account</th></tr></thead><tbody>{team.map((item) => <tr key={item.id}><td>{item.name}</td><td>{item.email}</td><td><span className={stageClass(item.role)}>{item.role.replaceAll('_', ' ')}</span></td><td>{item.active ? 'Active' : 'Disabled'}</td></tr>)}{!team.length && <tr><td colSpan={4} className="empty-state">Team access is available to organisation administrators.</td></tr>}</tbody></table></div><div className="permission-grid"><b>Role access</b><span>Recruiter: candidates, jobs, screening, interview scheduling, draft offers, tasks</span><span>Hiring manager: organisation pipeline, interviewer feedback, offer approval, audit</span><span>Interviewer: assigned interviews and feedback</span><span>Admin: team provisioning, settings, recruiter actions and audit</span></div></section>
}

function SettingsView({ settings, canEdit, onSave }: { settings: Settings | null; canEdit: boolean; onSave: (event: FormEvent<HTMLFormElement>) => void }) {
  return <section className="pipeline-panel"><div className="section-title"><div><h2>Organisation and privacy defaults</h2><p>Retention is recorded as a policy value; scheduled deletion jobs are not enabled yet.</p></div></div><form className="form-grid settings-form" onSubmit={onSave}><Field label="Default timezone"><input name="timezone" defaultValue={settings?.timezone ?? 'UTC'} required disabled={!canEdit} /></Field><Field label="Candidate retention (days)"><input name="retention_days" type="number" min="30" max="3650" defaultValue={settings?.retention_days ?? 365} disabled={!canEdit} /></Field><Field label="Careers page introduction" wide><textarea name="careers_intro" rows={3} defaultValue={settings?.careers_intro ?? ''} disabled={!canEdit} /></Field><Field label="Application consent"><span className="check-field"><input name="require_candidate_consent" type="checkbox" defaultChecked={settings?.require_candidate_consent ?? true} disabled={!canEdit} />Require candidate consent before applications are stored</span></Field>{canEdit && <div className="modal-actions"><button className="button primary">Save settings</button></div>}<p className="form-disclaimer wide-field">Encryption, candidate export/deletion execution, and retention automation must be enabled before production use.</p></form></section>
}

function AuditView({ events }: { events: AuditEvent[] }) {
  return <section className="candidate-section"><div className="section-title candidate-title"><div><h2>Recent organisation activity</h2><p>Latest candidate, job, interview, offer and settings events.</p></div></div><div className="audit-list">{events.map((item) => <article className="audit-row" key={item.id}><time>{formatDate(item.created_at)}</time><b>{item.action.replaceAll('_', ' ')}</b><span>{item.entity_type} · {item.entity_id.slice(0, 8)}</span><small>{JSON.stringify(item.details)}</small></article>)}{!events.length && <p className="empty-state">No audit events recorded yet.</p>}</div></section>
}

function MessagesView({ templates, candidates, outbox, canCreate, onSaveTemplate, onCreateDraft }: { templates: EmailTemplate[]; candidates: Candidate[]; outbox: DraftMessage[]; canCreate: boolean; onSaveTemplate: (payload: Omit<EmailTemplate, 'id'>, templateId?: string) => void; onCreateDraft: (payload: { template_id: string; candidate_id: string; subject?: string; body?: string }) => void }) {
  const [templateId, setTemplateId] = useState('')
  const [candidateId, setCandidateId] = useState('')
  const [templateName, setTemplateName] = useState('')
  const [templateSubject, setTemplateSubject] = useState('')
  const [templateBody, setTemplateBody] = useState('')
  const [eventKey, setEventKey] = useState('interview_invitation')
  const [editingTemplateId, setEditingTemplateId] = useState('')
  const selectedTemplate = templates.find((item) => item.id === templateId)
  const selectedCandidate = candidates.find((item) => item.id === candidateId)
  return <div className="message-layout"><section className="pipeline-panel"><div className="section-title"><div><h2>Message draft</h2><p>Personalise a template for a candidate. Drafts are not delivered.</p></div><span className="stage-pill stage-screening">No email provider</span></div><form className="form-grid message-form" onSubmit={(event) => { event.preventDefault(); if (templateId && candidateId) onCreateDraft({ template_id: templateId, candidate_id: candidateId }) }}><Field label="Template"><select value={templateId} onChange={(event) => setTemplateId(event.target.value)} required><option value="">Choose template</option>{templates.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field><Field label="Candidate"><select value={candidateId} onChange={(event) => setCandidateId(event.target.value)} required><option value="">Choose candidate</option>{candidates.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.role_title}</option>)}</select></Field><Field label="Subject preview" wide><input readOnly value={selectedTemplate?.subject.replaceAll('{{candidate}}', selectedCandidate?.name ?? '{{candidate}}').replaceAll('{{role}}', selectedCandidate?.role_title ?? '{{role}}') ?? ''} /></Field><Field label="Body preview" wide><textarea readOnly rows={6} value={selectedTemplate?.body.replaceAll('{{candidate}}', selectedCandidate?.name ?? '{{candidate}}').replaceAll('{{role}}', selectedCandidate?.role_title ?? '{{role}}').replaceAll('{{compensation}}', selectedCandidate?.expected_ctc ?? '{{compensation}}') ?? ''} /></Field>{canCreate && <div className="modal-actions"><button className="button primary" disabled={!templateId || !candidateId}>Save draft</button></div>}</form><div className="integration-grid"><article className="integration-card"><Mail size={19} /><b>Transactional email</b><span>Verified sender domain, provider credentials and delivery webhooks are required to send.</span></article><article className="integration-card"><CalendarDays size={19} /><b>Calendar and meetings</b><span>Google Workspace or Microsoft Graph credentials are required to create events and links.</span></article></div></section><section className="pipeline-panel"><div className="section-title"><div><h2>Templates</h2><p>Tenant-specific editable message content</p></div></div><div className="template-list">{templates.map((template) => <article className="template-row" key={template.id}><span className="stage-pill stage-new">{template.event_key.replaceAll('_', ' ')}</span><b>{template.name}</b><small>{template.subject}</small>{canCreate && <button className="action-link" onClick={() => { setEditingTemplateId(template.id); setTemplateName(template.name); setTemplateSubject(template.subject); setTemplateBody(template.body); setEventKey(template.event_key) }}>Edit</button>}</article>)}{!templates.length && <p className="empty-state">Templates are loading or unavailable.</p>}</div>{canCreate && <form className="form-grid template-form" onSubmit={(event) => { event.preventDefault(); onSaveTemplate({ name: templateName, subject: templateSubject, body: templateBody, event_key: eventKey }, editingTemplateId || undefined); setEditingTemplateId(''); setTemplateName(''); setTemplateSubject(''); setTemplateBody('') }}><h3 className="wide-field">{editingTemplateId ? 'Edit template' : 'Add template'}</h3><Field label="Template name"><input value={templateName} onChange={(event) => setTemplateName(event.target.value)} required /></Field><Field label="Trigger"><select value={eventKey} onChange={(event) => setEventKey(event.target.value)}><option value="application_received">Application received</option><option value="interview_invitation">Interview invitation</option><option value="rejection">Rejection</option><option value="offer">Offer</option></select></Field><Field label="Subject"><input value={templateSubject} onChange={(event) => setTemplateSubject(event.target.value)} required /></Field><Field label="Body" wide><textarea rows={4} value={templateBody} onChange={(event) => setTemplateBody(event.target.value)} required /></Field><p className="form-disclaimer wide-field">Available placeholders: {'{{candidate}}'}, {'{{role}}'}, {'{{compensation}}'}</p><div className="modal-actions"><button type="button" className="button outline" onClick={() => { setEditingTemplateId(''); setTemplateName(''); setTemplateSubject(''); setTemplateBody('') }}>Cancel</button><button className="button primary">{editingTemplateId ? 'Update template' : 'Save template'}</button></div></form>}</section><section className="candidate-section outbox-section"><div className="section-title candidate-title"><div><h2>Draft outbox</h2><p>Saved message drafts. None have been sent.</p></div></div><div className="table-scroll"><table><thead><tr><th>Recipient</th><th>Subject</th><th>Status</th><th>Created</th></tr></thead><tbody>{outbox.map((message) => <tr key={message.id}><td>{message.recipient}</td><td>{message.subject}</td><td><span className={stageClass(message.status)}>{message.status}</span></td><td>{formatDate(message.created_at)}</td></tr>)}{!outbox.length && <tr><td colSpan={4} className="empty-state">No message drafts yet.</td></tr>}</tbody></table></div></section></div>
}

function WorkflowModal({ kind, candidates, jobs, team, selectedCandidateId, onClose, onSubmit }: { kind: 'candidate' | 'job' | 'screening' | 'interview' | 'feedback' | 'offer' | 'task' | 'team'; candidates: Candidate[]; jobs: Job[]; team: TeamUser[]; selectedCandidateId: string; onClose: () => void; onSubmit: (event: FormEvent<HTMLFormElement>, endpoint: string, success: string, method?: string, transform?: (form: FormData) => unknown) => void }) {
  const titles = { candidate: 'Add candidate', job: 'Create job', screening: 'Telephone screening', interview: 'Schedule interview', feedback: 'Interview feedback', offer: 'Prepare offer', task: 'Create recruiter task', team: 'Add team member' }
  function endpointAndSuccess(form: FormData) {
    if (kind === 'candidate') return ['/candidates', 'Candidate added to the pipeline', 'POST', (values: FormData) => ({ name: values.get('name'), email: values.get('email'), role_title: values.get('role_title'), stage: values.get('stage'), experience: values.get('experience'), skills: String(values.get('skills') ?? '').split(',').map((skill) => skill.trim()).filter(Boolean), current_ctc: values.get('current_ctc'), expected_ctc: values.get('expected_ctc'), availability: values.get('availability') })] as const
    if (kind === 'job') return ['/jobs', 'Job requisition created', 'POST', (values: FormData) => ({ title: values.get('title'), location: values.get('location'), employment_type: values.get('employment_type'), status: values.get('status'), description: values.get('description'), requirements: String(values.get('requirements') ?? '').split(',').map((requirement) => requirement.trim()).filter(Boolean).map((skill) => ({ skill, category: String(values.get('must_have') ?? '').split(',').map((item) => item.trim()).includes(skill) ? 'must_have' : 'nice_to_have', weight: 1, min_evidence_level: 1 })) })] as const
    if (kind === 'screening') return [`/candidates/${selectedCandidateId}/screenings`, 'Screening notes and decision saved', 'POST', (values: FormData) => ({ ...Object.fromEntries(values.entries()) })] as const
    if (kind === 'interview') return ['/interviews', 'Interview saved. Calendar event and invite were not created.', 'POST', (values: FormData) => ({ ...Object.fromEntries(values.entries()), scheduled_for: new Date(String(values.get('scheduled_for'))).toISOString(), duration_minutes: Number(values.get('duration_minutes')), interviewer_id: values.get('interviewer_id') || null, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone })] as const
    if (kind === 'feedback') return [`/interviews/${valuesId(form)}/feedback`, 'Structured interview feedback submitted', 'POST', (values: FormData) => ({ technical_rating: Number(values.get('technical_rating')), problem_solving_rating: Number(values.get('problem_solving_rating')), evidence: values.get('evidence'), recommendation: values.get('recommendation') })] as const
    if (kind === 'offer') return ['/offers', 'Offer draft created. It requires an approver; no email was sent.', 'POST', (values: FormData) => ({ candidate_id: values.get('candidate_id'), title: values.get('title'), compensation: values.get('compensation'), employment_type: values.get('employment_type'), joining_date: values.get('joining_date'), expires_at: values.get('expires_at') || null })] as const
    if (kind === 'task') return ['/tasks', 'Recruiter task created', 'POST', (values: FormData) => ({ title: values.get('title'), candidate_id: values.get('candidate_id') || null, assigned_to_id: values.get('assigned_to_id') || null, due_at: values.get('due_at') || null })] as const
    return ['/users', 'Team member account created', 'POST', (values: FormData) => Object.fromEntries(values.entries())] as const
  }
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    const values = new FormData(event.currentTarget)
    const [path, success, method, transform] = endpointAndSuccess(values)
    onSubmit(event, path, success, method, transform as (form: FormData) => unknown)
  }
  return <div className="modal-backdrop" onClick={(event) => { if (event.target === event.currentTarget) onClose() }}><section className="form-modal"><div className="modal-heading"><div><p className="eyebrow">HIRING WORKFLOW</p><h2>{titles[kind]}</h2></div><button className="icon-button" onClick={onClose}><X size={19} /></button></div>
    {kind === 'candidate' && <form className="form-grid" onSubmit={handleSubmit}><Field label="Full name"><input name="name" required maxLength={180} /></Field><Field label="Email"><input name="email" type="email" required /></Field><Field label="Role"><input name="role_title" list="job-titles" required /> <datalist id="job-titles">{jobs.map((job) => <option key={job.id}>{job.title}</option>)}</datalist></Field><Field label="Stage"><select name="stage"><option>New</option><option>Recruiter Review</option><option>Screening</option></select></Field><Field label="Experience"><input name="experience" placeholder="e.g. 3 years" /></Field><Field label="Availability"><input name="availability" placeholder="e.g. 30 days" /></Field><Field label="Current compensation"><input name="current_ctc" /></Field><Field label="Expected compensation"><input name="expected_ctc" /></Field><Field label="Skills, comma-separated" wide><input name="skills" placeholder="Python, SQL, APIs" /></Field><ModalActions onClose={onClose} label="Add candidate" /></form>}
    {kind === 'job' && <form className="form-grid" onSubmit={handleSubmit}><Field label="Job title"><input name="title" required /></Field><Field label="Location"><input name="location" placeholder="City, hybrid or remote" /></Field><Field label="Employment type"><select name="employment_type"><option>Full time</option><option>Contract</option><option>Internship</option><option>Part time</option></select></Field><Field label="Initial status"><select name="status"><option>draft</option><option>published</option></select></Field><Field label="Requirements, comma-separated" wide><input name="requirements" placeholder="Python, FastAPI, PostgreSQL" required /></Field><Field label="Must-have skills, comma-separated" wide><input name="must_have" placeholder="Python, FastAPI" /></Field><Field label="Role description" wide><textarea name="description" rows={5} /></Field><p className="form-disclaimer wide-field">Skill weights default evenly. Matching is deterministic and profile-only until verified resume evidence is configured.</p><ModalActions onClose={onClose} label="Create role" /></form>}
    {kind === 'screening' && <form className="form-grid" onSubmit={handleSubmit}><Field label="Call status"><select name="call_status"><option>Connected</option><option>No answer</option><option>Call back requested</option></select></Field><Field label="Notice / joining period"><input name="notice_period" placeholder="e.g. 30 days" /></Field><Field label="Current compensation"><input name="current_ctc" /></Field><Field label="Expected compensation"><input name="expected_ctc" /></Field><Field label="Relocation"><select name="relocation"><option>Not discussed</option><option>Yes</option><option>No</option><option>Needs discussion</option></select></Field><Field label="Contract preference"><select name="contract_preference"><option>Not discussed</option><option>Yes</option><option>No</option><option>Needs discussion</option></select></Field><Field label="Recruiter notes" wide><textarea name="notes" rows={4} maxLength={5000} /></Field><Field label="Decision"><select name="decision"><option>Shortlist</option><option>Hold</option><option>Reject</option></select></Field><ModalActions onClose={onClose} label="Save screening" /></form>}
    {kind === 'interview' && <form className="form-grid" onSubmit={handleSubmit}><Field label="Candidate"><select name="candidate_id" defaultValue={selectedCandidateId} required><option value="">Select candidate</option>{candidates.map((item) => <option value={item.id} key={item.id}>{item.name} · {item.role_title}</option>)}</select></Field><Field label="Round"><select name="title"><option>Technical Round 1</option><option>Technical Round 2</option><option>Final Discussion</option><option>Recruiter Screen</option></select></Field><Field label="Interviewer"><select name="interviewer_id"><option value="">Unassigned</option>{team.filter((item) => ['interviewer', 'hiring_manager', 'admin'].includes(item.role)).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field><Field label="Date and time"><input name="scheduled_for" type="datetime-local" required /></Field><Field label="Duration"><select name="duration_minutes"><option value="30">30 minutes</option><option value="45">45 minutes</option><option value="60">60 minutes</option><option value="90">90 minutes</option></select></Field><Field label="Method"><select name="meeting_method"><option>In person</option><option>Phone</option><option>Google Meet</option><option>Microsoft Teams</option></select></Field><Field label="Meeting link or location" wide><input name="location_or_link" placeholder="Room or provider-created link" /></Field><p className="form-disclaimer wide-field">This stores the interview schedule only. No external calendar event, meeting link, or email is created.</p><ModalActions onClose={onClose} label="Save schedule" /></form>}
    {kind === 'feedback' && <form className="form-grid" onSubmit={handleSubmit}><input type="hidden" name="interview_id" value={selectedCandidateId} /><Field label="Technical skills"><select name="technical_rating"><option value="5">5 · Excellent</option><option value="4">4 · Strong</option><option value="3">3 · Good</option><option value="2">2 · Developing</option><option value="1">1 · Weak</option></select></Field><Field label="Problem solving"><select name="problem_solving_rating"><option value="5">5 · Excellent</option><option value="4">4 · Strong</option><option value="3">3 · Good</option><option value="2">2 · Developing</option><option value="1">1 · Weak</option></select></Field><Field label="Recommendation"><select name="recommendation"><option>Strong yes</option><option>Yes</option><option>Hold</option><option>No</option></select></Field><Field label="Evidence from interview" wide><textarea name="evidence" minLength={10} rows={5} required placeholder="Specific examples and observed evidence" /></Field><ModalActions onClose={onClose} label="Submit scorecard" /></form>}
    {kind === 'offer' && <form className="form-grid" onSubmit={handleSubmit}><Field label="Candidate"><select name="candidate_id" defaultValue={selectedCandidateId} required><option value="">Select candidate</option>{candidates.map((item) => <option value={item.id} key={item.id}>{item.name} · {item.role_title}</option>)}</select></Field><Field label="Position title"><input name="title" required /></Field><Field label="Compensation"><input name="compensation" required placeholder="e.g. ₹8 LPA" /></Field><Field label="Employment type"><select name="employment_type"><option>Full time</option><option>Contract</option><option>Internship</option></select></Field><Field label="Joining date"><input name="joining_date" type="date" /></Field><Field label="Offer expiry"><input name="expires_at" type="datetime-local" /></Field><p className="form-disclaimer wide-field">Drafts need hiring-manager/admin approval. Candidate acceptance uses a private link; no email or signed document is generated here.</p><ModalActions onClose={onClose} label="Save offer draft" /></form>}
    {kind === 'task' && <form className="form-grid" onSubmit={handleSubmit}><Field label="Follow-up"><input name="title" required placeholder="Call candidate to confirm availability" /></Field><Field label="Due"><input name="due_at" type="datetime-local" /></Field><Field label="Candidate"><select name="candidate_id"><option value="">Organisation task</option>{candidates.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field><Field label="Assign to"><select name="assigned_to_id"><option value="">Me</option>{team.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field><ModalActions onClose={onClose} label="Create task" /></form>}
    {kind === 'team' && <form className="form-grid" onSubmit={handleSubmit}><Field label="Name"><input name="name" required minLength={2} /></Field><Field label="Work email"><input name="email" type="email" required /></Field><Field label="Temporary password"><input name="password" type="password" minLength={12} required /></Field><Field label="Role"><select name="role"><option value="recruiter">Recruiter</option><option value="hiring_manager">Hiring manager</option><option value="interviewer">Interviewer</option><option value="admin">Administrator</option></select></Field><p className="form-disclaimer wide-field">This creates an account with the password entered here. Send credentials through a secure channel and ask the user to change it; email invitations and password reset are not connected.</p><ModalActions onClose={onClose} label="Create account" /></form>}
  </section></div>
}

function valuesId(form: FormData) { return String(form.get('interview_id') ?? '') }
function ModalActions({ onClose, label }: { onClose: () => void; label: string }) { return <div className="modal-actions"><button type="button" className="button outline" onClick={onClose}>Cancel</button><button className="button primary">{label}</button></div> }

function PublicApplication({ jobId, jobs, onDone, onError }: { jobId: string; jobs: PublicJob[]; onDone: (message: string) => void; onError: (message: string) => void }) {
  const [submitted, setSubmitted] = useState('')
  const job = jobs.find((item) => item.id === jobId)
  if (submitted) return <div className="modal-backdrop"><section className="form-modal"><span className="success-symbol"><Check size={20} /></span><p className="eyebrow">APPLICATION RECEIVED</p><h2>Thanks for applying.</h2><p>{submitted}</p><button className="button outline" onClick={() => { window.history.pushState({}, '', '/careers'); window.location.reload() }}>Back to openings</button></section></div>
  if (!job) return <div className="modal-backdrop"><section className="form-modal"><h2>Apply for a role</h2><p>This role is no longer available.</p><button className="button outline" onClick={() => { window.history.pushState({}, '', '/careers'); window.location.reload() }}>Back to careers</button></section></div>
  const activeJob = job
  async function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget)
    try {
      const response = await api<{ message: string; portal_url: string }>(`/public/jobs/${activeJob.id}/applications`, '', { method: 'POST', body: JSON.stringify({ name: form.get('name'), email: form.get('email'), experience: form.get('experience'), skills: String(form.get('skills') ?? '').split(',').map((skill) => skill.trim()).filter(Boolean), availability: form.get('availability'), consent: form.get('consent') === 'on' }) })
      onDone(response.message); setSubmitted(`${response.message} Save your private status link: ${window.location.origin}${response.portal_url}`)
    } catch (cause) { onError(errorText(cause)) }
  }
  return <div className="modal-backdrop"><section className="form-modal"><button className="action-link back-link" onClick={() => { window.history.pushState({}, '', '/careers'); window.location.reload() }}><ArrowLeft size={14} />All openings</button><p className="eyebrow">APPLICATION</p><h2>{activeJob.title}</h2><p>{activeJob.organization_name} · {activeJob.location} · {activeJob.employment_type}</p><form className="form-grid" onSubmit={apply}><Field label="Full name"><input name="name" required /></Field><Field label="Email"><input name="email" type="email" required /></Field><Field label="Experience"><input name="experience" /></Field><Field label="Availability"><input name="availability" /></Field><Field label="Skills, comma-separated" wide><input name="skills" placeholder="Python, PostgreSQL" /></Field><label className="consent-field wide-field"><input name="consent" type="checkbox" required />I consent to this organisation processing my application data for recruitment.</label><ModalActions onClose={() => { window.history.pushState({}, '', '/careers'); window.location.reload() }} label="Submit application" /></form></section></div>
}

export default App
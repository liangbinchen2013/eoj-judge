import { useAuthStore } from '../store/auth';
import { getDeviceFingerprint } from '../utils/deviceFingerprint';

const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1';

export interface AIModelConfig {
  id: string;
  model: string;
  display_name: string;
  enabled: boolean;
  temperature?: string;
  max_tokens?: string;
}

interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    message: string;
    code: string;
  };
}

// ── Shared ──
interface Pagination {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

// ── User ──
export interface User {
  id: number;
  username: string;
  role: string;
  permissions?: string[];
  avatar_url?: string;
  created_at?: string;
  email?: string;
  bio?: string;
  signature?: string;
  experience?: number;
  level?: number;
  banned?: number;
  github_id?: number;
  cpoauth_id?: string;
  rating?: number;
  max_rating?: number;
  follower_count?: number;
  following_count?: number;
}

interface UserStats {
  solved_count: number;
  submission_count: number;
  accepted_count: number;
  rating?: number;
  max_rating?: number;
  rank?: number;
}

// ── Problem ──
interface ProblemBase {
  id: number;
  slug: string;
  title: string;
  difficulty?: string;
  rating?: number;
  tags?: string;
  time_limit: number;
  memory_limit: number;
  judge_type?: string;
  is_public?: number;
  created_at?: string;
  updated_at?: string;
}

export interface ProblemListItem extends ProblemBase {
  pass_rate?: number | null;
  submission_count?: number;
  accepted_count?: number;
}

interface Problem extends ProblemBase {
  description: string;
  input_format?: string;
  output_format?: string;
  sample_input?: string;
  sample_output?: string;
  spj_language?: string;
  pass_rate?: number | null;
  submission_count?: number;
  accepted_count?: number;
}

interface ProblemStats {
  submission_count: number;
  accepted_count: number;
  pass_rate: number | null;
}

interface Testcase {
  id?: number;
  input: string;
  expected_output: string;
  is_sample?: number | boolean;
  score?: number;
  sort_order?: number;
}

// ── Submission ──
interface Submission {
  id: number;
  user_id?: number;
  problem_id: number;
  language: string;
  status: string;
  score: number;
  time_used?: number;
  memory_used?: number;
  source_code?: string;
  details?: string;
  created_at: string;
  updated_at?: string;
  contest_id?: number;
  username?: string;
  problem_title?: string;
  problem_slug?: string;
}

interface SubmissionTestcase {
  id?: number;
  status: string;
  time_used?: number;
  memory_used?: number;
  score?: number;
  detail?: string;
  sort_order?: number;
}

interface JudgeLog {
  id: number;
  submission_id: number;
  log_type: string;
  message: string;
  created_at: string;
}

// ── Contest ──
export interface Contest {
  id: number;
  title: string;
  description?: string;
  start_time: string;
  end_time: string;
  status?: string;
  is_public?: number;
  created_by?: number;
  scoring_type?: string;
  is_rated?: number;
  allow_virtual?: number;
  duration_minutes?: number;
  rating_finalized?: number;
  participant_count?: number;
  is_registered?: boolean;
  created_at?: string;
  updated_at?: string;
}

interface ContestProblem {
  id: number;
  contest_id: number;
  problem_id: number;
  label?: string;
  score?: number;
  title?: string;
  slug?: string;
}

interface ContestRanking {
  rank: number;
  user_id: number;
  username: string;
  avatar_url?: string;
  score: number;
  problems?: Record<string, { status: string; score: number; attempts?: number }>;
}

// ── Ticket ──
interface Ticket {
  id: number;
  user_id: number;
  title: string;
  content: string;
  category?: string;
  status: string;
  priority?: string;
  created_at: string;
  updated_at?: string;
  username?: string;
}

interface TicketReply {
  id: number;
  ticket_id: number;
  user_id: number;
  content: string;
  created_at: string;
  username?: string;
}

// ── Problem List ──
export interface ProblemList {
  id: number;
  title: string;
  description?: string;
  user_id: number;
  is_public?: number;
  created_at?: string;
  updated_at?: string;
  username?: string;
  problem_count?: number;
}

interface ProblemListEntry {
  id: number;
  list_id: number;
  problem_id: number;
  sort_order?: number;
  note?: string;
  title?: string;
  slug?: string;
  difficulty?: string;
}

// ── Solution ──
interface Solution {
  id: number;
  problem_id: number;
  user_id: number;
  title: string;
  content: string;
  language?: string;
  vote_count: number;
  view_count: number;
  review_status?: string;
  reject_reason?: string;
  created_at: string;
  updated_at?: string;
  username?: string;
  problem_title?: string;
  is_voted?: boolean;
}

// ── Discussion ──
export interface Discussion {
  id: number;
  problem_id?: number;
  user_id: number;
  title: string;
  content: string;
  category?: string;
  reply_count: number;
  view_count: number;
  is_pinned?: number;
  created_at: string;
  updated_at?: string;
  username?: string;
  problem_title?: string;
}

interface DiscussionReply {
  id: number;
  discussion_id: number;
  user_id: number;
  content: string;
  created_at: string;
  username?: string;
}

// ── Team ──
interface Team {
  id: number;
  name: string;
  slug: string;
  description?: string;
  avatar_url?: string;
  owner_id: number;
  is_public?: number;
  join_method?: string;
  created_at?: string;
  updated_at?: string;
  member_count?: number;
  username?: string;
}

interface TeamMember {
  id: number;
  team_id: number;
  user_id: number;
  role: string;
  joined_at: string;
  username?: string;
  avatar_url?: string;
}

interface TeamAnnouncement {
  id: number;
  team_id: number;
  user_id: number;
  title: string;
  content: string;
  is_pinned?: number;
  created_at: string;
  updated_at?: string;
  username?: string;
}

interface TeamDiscussion {
  id: number;
  team_id: number;
  user_id: number;
  title: string;
  content: string;
  is_pinned?: number;
  reply_count: number;
  view_count: number;
  created_at: string;
  updated_at?: string;
  username?: string;
}

interface TeamDiscussionReply {
  id: number;
  discussion_id: number;
  user_id: number;
  content: string;
  created_at: string;
  username?: string;
}

interface TeamProblemSet {
  id: number;
  team_id: number;
  user_id: number;
  title: string;
  description?: string;
  is_public?: number;
  created_at?: string;
  updated_at?: string;
}

interface TeamContest {
  id: number;
  team_id: number;
  user_id: number;
  title: string;
  description?: string;
  start_time: string;
  end_time: string;
  scoring_type?: string;
  is_public?: number;
  status?: string;
  created_at?: string;
  updated_at?: string;
  participant_count?: number;
  is_registered?: boolean;
}

interface TeamJoinRequest {
  id: number;
  team_id: number;
  user_id: number;
  message?: string;
  status: string;
  created_at: string;
  username?: string;
  avatar_url?: string;
}

// ── Blog ──
interface Blog {
  id: number;
  user_id: number;
  title: string;
  content: string;
  tags?: string;
  status?: string;
  view_count: number;
  like_count: number;
  comment_count: number;
  created_at: string;
  updated_at?: string;
  username?: string;
  avatar_url?: string;
  liked?: boolean;
}

interface BlogComment {
  id: number;
  blog_id: number;
  user_id: number;
  content: string;
  created_at: string;
  username?: string;
  avatar_url?: string;
}

// ── Notification ──
export interface AppNotification {
  id: number;
  user_id: number;
  type: string;
  title: string;
  content?: string;
  link?: string;
  is_read?: number;
  created_at: string;
}

// ── Conversation / Message ──
interface Conversation {
  id: number;
  created_at?: string;
  updated_at?: string;
  last_message?: string;
  last_message_at?: string;
  other_user?: User;
  unread_count?: number;
}

interface Message {
  id: number;
  conversation_id: number;
  sender_id: number;
  content: string;
  created_at: string;
}

// ── Training ──
export interface TrainingPlan {
  id: number;
  title: string;
  description?: string;
  cover_image?: string;
  category?: string;
  difficulty?: string;
  user_id: number;
  is_official?: number;
  sort_order?: number;
  created_at?: string;
  updated_at?: string;
  username?: string;
  chapter_count?: number;
  problem_count?: number;
  joined?: boolean;
  progress?: number;
  chapters?: TrainingChapter[];
}

export interface TrainingChapter {
  id: number;
  plan_id: number;
  title: string;
  description?: string;
  sort_order?: number;
  problems?: TrainingChapterProblem[];
}

export interface TrainingChapterProblem {
  id: number;
  chapter_id: number;
  problem_id: number;
  sort_order?: number;
  note?: string;
  title?: string;
  slug?: string;
  difficulty?: string;
  solved?: boolean;
}

// ── Plagiarism ──
interface PlagiarismReport {
  id: number;
  contest_id?: number;
  submission_a: number;
  submission_b: number;
  similarity: number;
  method?: string;
  created_at: string;
  user_a?: string;
  user_b?: string;
}

// ── Problem Report ──
interface ProblemReport {
  id: number;
  problem_id: number;
  user_id: number;
  type: string;
  description: string;
  status: string;
  admin_reply?: string;
  created_at: string;
  updated_at?: string;
  username?: string;
  problem_title?: string;
}

// ── Collection ──
export interface ProblemCollection {
  id: number;
  user_id: number;
  name: string;
  description?: string;
  is_public?: number;
  sort_order?: number;
  created_at?: string;
  updated_at?: string;
  item_count?: number;
  problem_count?: number;
}

export interface CollectionItem {
  id: number;
  collection_id: number;
  problem_id: number;
  note?: string;
  sort_order?: number;
  title?: string;
  slug?: string;
  difficulty?: string;
  created_at?: string;
  tags?: string;
}

// ── Upload ──
interface Upload {
  id: number;
  user_id: number;
  filename: string;
  original_name: string;
  file_type: string;
  mime_type?: string;
  size_bytes: number;
  url?: string;
  created_at: string;
}

// ── Achievement ──
interface Achievement {
  key?: string;
  title: string;
  description?: string;
  icon?: string;
  achieved?: boolean;
  achieved_at?: string;
}

// ── Note ──
interface ProblemNote {
  id?: number;
  user_id?: number;
  problem_id: number;
  content: string;
  is_public?: number;
  created_at?: string;
  updated_at?: string;
}

// ── Code Template ──
interface CodeTemplate {
  id?: number;
  user_id?: number;
  language: string;
  content: string;
  name?: string;
  created_at?: string;
  updated_at?: string;
}

// ── Audit / Ban ──
interface AuditLog {
  id: number;
  user_id?: number;
  username?: string;
  ip: string;
  device_fingerprint?: string;
  page?: string;
  action: string;
  method: string;
  path: string;
  user_agent?: string;
  created_at: string;
}

interface BannedIP {
  id: number;
  ip: string;
  reason?: string;
  banned_by?: number;
  created_at: string;
}

interface BannedDevice {
  id: number;
  device_fingerprint: string;
  reason?: string;
  banned_by?: number;
  created_at: string;
}

// ── Rating ──
export interface RatingHistoryEntry {
  contest_id?: number;
  contest_title?: string;
  old_rating: number;
  new_rating: number;
  delta: number;
  reason?: string;
  created_at: string;
}

export interface RatingChange {
  user_id: number;
  username?: string;
  old_rating: number;
  new_rating: number;
  delta: number;
  rank?: number;
}

// ── Tags ──
interface TagCategory {
  id: number;
  name: string;
  slug: string;
  icon?: string;
  sort_order?: number;
  tags?: Tag[];
}

interface Tag {
  id: number;
  category_id?: number;
  name: string;
  slug: string;
  sort_order?: number;
  problem_count?: number;
}

// ── Recommendation ──
export interface RecommendedProblem {
  problem_id: number;
  title: string;
  slug: string;
  difficulty?: string;
  rating?: number;
  reason: string;
  score?: number;
  tags?: string[];
}

// ── Search ──
interface SearchResult {
  type: string;
  id: number;
  title: string;
  url?: string;
  subtitle?: string;
  snippet?: string;
}

export interface SearchSuggestion {
  type: string;
  text?: string;
  url?: string;
  id?: number;
  title?: string;
  subtitle?: string;
  avatar_url?: string;
}

// ── SQL Admin ──
interface TableColumn {
  cid: number;
  name: string;
  type: string;
  notnull: number;
  dflt_value: string | null;
  pk: number;
}

// ── AI ──
interface AIToolCall {
  name: string;
  arguments: Record<string, unknown>;
  result_summary: string;
}

// Shape of streamed event data. Fields are unioned because the server emits
// different payloads per event type; consumers only read fields matching the
// `type` they branched on, so the widened contract is safe at runtime.
export interface AIStreamData {
  content?: string;
  name?: string;
  arguments?: Record<string, unknown>;
  result_summary?: string;
  tool_calls?: AIToolCall[];
  message?: string;
  [key: string]: unknown;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private getToken(): string | null {
    return localStorage.getItem('token');
  }

  private async request<T>(path: string, options: RequestInit = {}, skipJsonBody?: boolean): Promise<T> {
    const token = this.getToken();
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    if (!skipJsonBody) {
      headers['Content-Type'] = 'application/json';
    }

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    // Add device fingerprint header
    try {
      const fingerprint = await getDeviceFingerprint();
      if (fingerprint) {
        headers['X-Device-Fingerprint'] = fingerprint;
      }
    } catch { /* ignore */ }

    // Retry logic: retry up to 2 times on network errors or 5xx
    const MAX_RETRIES = 2;
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const response = await fetch(`${this.baseUrl}${path}`, {
          ...options,
          headers,
        });

        // Auto-logout on 401
        if (response.status === 401 && token) {
          localStorage.removeItem('token');
          window.dispatchEvent(new Event('auth:expired'));
          throw new Error('Session expired. Please login again.');
        }

        // Retry on server errors (5xx) that aren't 504 timeouts
        if (response.status >= 500 && response.status < 600 && attempt < MAX_RETRIES) {
          // Wait with exponential backoff: 1s, 2s
          await new Promise(r => setTimeout(r, (attempt + 1) * 1000));
          continue;
        }

        const result: ApiResponse<T> = await response.json().catch(() => ({
          success: false,
          error: {
            message: 'Failed to parse response',
            code: 'PARSE_ERROR'
          }
        }));

        if (!result.success || !response.ok) {
          const message = result.error?.message || `HTTP ${response.status}`;
          throw new Error(message);
        }

        if (result.data === undefined) {
          throw new Error('No data in response');
        }

        return result.data;
      } catch (e: unknown) {
        // Network errors: retry
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.includes('Network error') && attempt < MAX_RETRIES) {
          await new Promise(r => setTimeout(r, (attempt + 1) * 1000));
          continue;
        }
        // Non-retryable errors: rethrow immediately
        throw e;
      }
    }

    throw new Error('Network error. Please check your connection and try again.');
  }

  async getProblems(params?: { page?: number; pageSize?: number; search?: string; tag?: string; difficulty?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.search) query.set('search', params.search);
    if (params?.tag) query.set('tag', params.tag);
    if (params?.difficulty) query.set('difficulty', params.difficulty);
    return this.request<{ problems: ProblemListItem[]; pagination: Pagination }>(`/problems?${query.toString()}`);
  }

  async getProblemTags() {
    return this.request<{ tags: string[] }>('/problems/tags');
  }

  // Tag categories tree
  async getTagCategories() {
    return this.request<{ categories: TagCategory[] }>('/tags/categories');
  }

  // Tags tree with problem counts
  async getTagsTree() {
    return this.request<{ categories: TagCategory[] }>('/tags/problems/tags-tree');
  }

  // Problem-specific tags
  async getProblemTagsById(problemId: number) {
    return this.request<{ tags: Tag[] }>(`/problems/${problemId}/tags`);
  }

  // Set problem tags
  async setProblemTags(problemId: number, tagIds: number[]) {
    return this.request<{ message: string }>(`/problems/${problemId}/tags`, {
      method: 'PUT',
      body: JSON.stringify({ tag_ids: tagIds }),
    });
  }

  // Rating leaderboard
  async getRatingLeaderboard(params?: { page?: number; pageSize?: number }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    return this.request<{ rankings: RatingChange[]; pagination: Pagination }>(`/ratings/leaderboard?${query.toString()}`);
  }

  // User rating info
  async getUserRating(username: string) {
    return this.request<{ rating: number; max_rating: number; history: RatingHistoryEntry[] }>(`/users/${username}/rating`);
  }

  async getProblem(slug: string) {
    return this.request<{ problem: Problem; sampleTestcases: Testcase[]; stats: ProblemStats }>(`/problems/${slug}`);
  }

  async getProblemLanguages(slug: string) {
    return this.request<{ languages: string[] }>(`/problems/${slug}/languages`);
  }

  async getRelatedProblems(slug: string, limit = 5) {
    return this.request<{ problems: ProblemListItem[] }>(`/problems/${slug}/related?limit=${limit}`);
  }

  async createProblem(data: Record<string, unknown>) {
    return this.request<{ id: number; message: string }>('/problems', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateProblem(id: number, data: Record<string, unknown>) {
    return this.request<{ message: string }>(`/problems/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async addTestcases(problemId: number, testcases: Testcase[]) {
    return this.request<{ message: string; count: number }>(`/problems/${problemId}/testcases`, {
      method: 'POST',
      body: JSON.stringify(testcases),
    });
  }

  async submitCode(data: { problem_id: number; language: string; source_code: string; captcha_uuid?: string; captcha_answer?: string }) {
    return this.request<{ submission_id: number; status: string }>('/submissions', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getSubmissions(params?: { page?: number; pageSize?: number; problem_id?: string; status?: string; language?: string; user_id?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.problem_id) query.set('problem_id', params.problem_id);
    if (params?.status) query.set('status', params.status);
    if (params?.language) query.set('language', params.language);
    if (params?.user_id) query.set('user_id', params.user_id);
    return this.request<{ submissions: Submission[]; pagination: Pagination }>(`/submissions?${query.toString()}`);
  }

  async getSubmission(id: number) {
    return this.request<{ submission: Submission }>(`/submissions/${id}`);
  }

  async getSubmissionTestcases(id: number) {
    return this.request<{ testcases: SubmissionTestcase[] }>(`/submissions/${id}/testcases`);
  }

  async getSubmissionLogs(id: number) {
    return this.request<{ logs: JudgeLog[] }>(`/submissions/${id}/logs`);
  }

  async exportSubmissions(format: 'csv' | 'json' = 'csv') {
    return this.request<{ submissions?: Submission[] } | string>(`/submissions/export?format=${format}`);
  }

  async compareSubmissions(id1: number, id2: number) {
    return this.request<{ submission_a: Submission; submission_b: Submission }>(`/submissions/compare/${id1}/${id2}`);
  }

  async rejudgeSubmission(id: number) {
    return this.request<{ submission_id: number; status: string; message: string }>(`/submissions/${id}/rejudge`, {
      method: 'POST',
    });
  }

  async getMe() {
    return this.request<{ user: User }>('/auth/me');
  }

  async getCaptcha() {
    return this.request<{ uuid: string; png: string; type: 'text' | 'math'; answer_length: number }>('/captcha/generate');
  }

  async register(username: string, password: string, email?: string, captcha_uuid?: string, captcha_answer?: string, verification_code?: string) {
    return this.request<{ token: string }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password, email, captcha_uuid, captcha_answer, verification_code }),
    });
  }

  async sendVerificationCode(email: string) {
    return this.request<{ message: string; code?: string }>('/auth/send-verification-code', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  }

  async login(username: string, password: string, captcha_uuid?: string, captcha_answer?: string) {
    return this.request<{ token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password, captcha_uuid, captcha_answer }),
    });
  }

  async getRankings(limit?: number, timeRange?: string) {
    const query = new URLSearchParams();
    if (limit) query.set('limit', String(limit));
    if (timeRange) query.set('timeRange', timeRange);
    return this.request<{ rankings: RatingChange[] }>(`/rankings?${query.toString()}`);
  }

  async getUserProfile() {
    return this.request<{ user: User; stats: UserStats; recent_submissions: Submission[] }>('/users/profile');
  }

  async getUserSubmissions(params?: { page?: number; pageSize?: number; status?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.status) query.set('status', params.status);
    return this.request<{ submissions: Submission[]; pagination: Pagination }>(`/users/submissions?${query.toString()}`);
  }

  async getUserSolved() {
    return this.request<{ problems: ProblemListItem[] }>('/users/solved');
  }

  async getUserContests() {
    return this.request<{ contests: Contest[] }>('/users/contests');
  }

  async getUserByUsername(username: string) {
    return this.request<{ user: User; stats: UserStats; solved_problems: ProblemListItem[]; recent_submissions: Submission[] }>(`/users/${username}`);
  }

  async getProblemStatus(problemId: number) {
    return this.request<{ solved: boolean; attempted: boolean }>(`/problems/${problemId}/status`);
  }

  async checkFavorite(problemId: number) {
    return this.request<{ is_favorited: boolean }>(`/problems/${problemId}/favorite`);
  }

  async addFavorite(problemId: number) {
    return this.request<{ message: string }>(`/problems/${problemId}/favorite`, {
      method: 'POST',
    });
  }

  async removeFavorite(problemId: number) {
    return this.request<{ message: string }>(`/problems/${problemId}/favorite`, {
      method: 'DELETE',
    });
  }

  async getFavorites(params?: { page?: number; pageSize?: number }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    const qs = query.toString();
    return this.request<{ problems: ProblemListItem[]; pagination: Pagination }>(`/problems/user/favorites${qs ? `?${qs}` : ''}`);
  }

  // ── Problem Collections ──
  async getCollections() {
    return this.request<{ collections: ProblemCollection[] }>(`/collections`);
  }

  async createCollection(data: { name: string; description?: string; is_public?: boolean }) {
    return this.request<{ id: number; message: string }>('/collections', { method: 'POST', body: JSON.stringify(data) });
  }

  async updateCollection(id: number, data: Record<string, unknown>) {
    return this.request<{ message: string }>(`/collections/${id}`, { method: 'PUT', body: JSON.stringify(data) });
  }

  async deleteCollection(id: number) {
    return this.request<{ message: string }>(`/collections/${id}`, { method: 'DELETE' });
  }

  async getCollectionItems(id: number) {
    return this.request<{ collection: ProblemCollection; items: CollectionItem[] }>(`/collections/${id}/items`);
  }

  async addCollectionItem(collectionId: number, problemId: number, note?: string) {
    return this.request<{ message: string }>(`/collections/${collectionId}/items`, { method: 'POST', body: JSON.stringify({ problem_id: problemId, note }) });
  }

  async removeCollectionItem(collectionId: number, itemId: number) {
    return this.request<{ message: string }>(`/collections/${collectionId}/items/${itemId}`, { method: 'DELETE' });
  }

  async getUserList(params?: { page?: number; pageSize?: number; search?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.search) query.set('search', params.search);
    const qs = query.toString();
    return this.request<{ users: User[]; pagination: Pagination }>(`/users/list${qs ? `?${qs}` : ''}`);
  }

  async updateUserRole(userId: number, role: string) {
    return this.request<{ message: string }>(`/users/${userId}/role`, {
      method: 'PUT',
      body: JSON.stringify({ role }),
    });
  }

  async updateUserPermissions(userId: number, permissions: string[]) {
    return this.request<{ message: string }>(`/users/${userId}/permissions`, {
      method: 'PUT',
      body: JSON.stringify({ permissions }),
    });
  }

  async setUserBanned(userId: number, banned: boolean) {
    return this.request<{ message: string }>(`/users/${userId}/ban`, {
      method: 'PUT',
      body: JSON.stringify({ banned }),
    });
  }

  async getAdminStats() {
    return this.request<{
      users: number; problems: number; submissions: number; today_submissions: number;
      accepted: number; contests: number; lists: number; tickets: number; open_tickets: number;
      recent_submissions: Submission[];
    }>('/admin/stats');
  }

  async getAdminProblems(params?: { page?: number; pageSize?: number; search?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.search) query.set('search', params.search);
    return this.request<{ problems: ProblemListItem[]; pagination: Pagination }>(`/admin/problems?${query.toString()}`);
  }

  async exportProblems() {
    return this.request<{ problems: ProblemListItem[] }>('/admin/problems/export');
  }

  async importProblems(payload: Record<string, unknown>[]) {
    return this.request<{ imported: number; message: string }>('/admin/problems/import', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async deleteProblem(id: number) {
    return this.request<{ message: string }>(`/problems/${id}`, {
      method: 'DELETE',
    });
  }

  async getProblemTestcases(problemId: number) {
    return this.request<{ testcases: Testcase[] }>(`/problems/${problemId}/testcases`);
  }

  async deleteTestcase(problemId: number, index: number) {
    return this.request<{ message: string }>(`/problems/${problemId}/testcases/${index}`, {
      method: 'DELETE',
    });
  }

  async getProblemSpj(problemId: number) {
    return this.request<{ spj_code: string; spj_language: string }>(`/problems/${problemId}/spj`);
  }

  async updateProblemSpj(problemId: number, language: string, code: string) {
    return this.request<{ message: string }>(`/problems/${problemId}/spj`, {
      method: 'PUT',
      body: JSON.stringify({ language, code }),
    });
  }

  async deleteProblemSpj(problemId: number) {
    return this.request<{ message: string }>(`/problems/${problemId}/spj`, {
      method: 'DELETE',
    });
  }

  getGithubAuthUrl() {
    return `${this.baseUrl}/auth/github`;
  }

  // Contests
  async getContests(params?: { page?: number; pageSize?: number; status?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.status) query.set('status', params.status);
    return this.request<{ contests: Contest[]; pagination: Pagination }>(`/contests?${query.toString()}`);
  }

  async getContest(id: number) {
    return this.request<{ contest: Contest }>(`/contests/${id}`);
  }

  async createContest(data: Record<string, unknown>) {
    return this.request<{ id: number; message: string }>('/contests', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateContest(id: number, data: Record<string, unknown>) {
    return this.request<{ message: string }>(`/contests/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteContest(id: number) {
    return this.request<{ message: string }>(`/contests/${id}`, {
      method: 'DELETE',
    });
  }

  async getContestProblems(id: number) {
    return this.request<{ problems: ContestProblem[] }>(`/contests/${id}/problems`);
  }

  async registerContest(id: number) {
    return this.request<{ message: string }>(`/contests/${id}/register`, {
      method: 'POST',
    });
  }

  async getContestRankings(id: number) {
    return this.request<{
      rankings: ContestRanking[];
      problems: ContestProblem[];
      scoring_type?: string;
      is_rated?: number;
      rating_finalized?: number;
    }>(`/contests/${id}/rankings`);
  }

  async checkContestRegistration(id: number) {
    return this.request<{ registered: boolean }>(`/contests/${id}/registration`);
  }

  async getContestMyStatus(id: number) {
    return this.request<{ problems: Record<string, { status: string; score: number; best_score: number }> }>(`/contests/${id}/my-status`);
  }

  // Tickets
  async getTickets(params?: { page?: number; pageSize?: number; status?: string; category?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.status) query.set('status', params.status);
    if (params?.category) query.set('category', params.category);
    return this.request<{ tickets: Ticket[]; pagination: Pagination }>(`/tickets?${query.toString()}`);
  }

  async getTicket(id: number) {
    return this.request<{ ticket: Ticket; replies: TicketReply[] }>(`/tickets/${id}`);
  }

  async createTicket(data: { title: string; content: string; category?: string; priority?: string }) {
    return this.request<{ id: number; message: string }>('/tickets', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async replyTicket(id: number, content: string) {
    return this.request<{ message: string }>(`/tickets/${id}/replies`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
  }

  async updateTicketStatus(id: number, data: { status?: string; priority?: string }) {
    return this.request<{ message: string }>(`/tickets/${id}/status`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  // Problem Lists
  async getProblemLists(params?: { page?: number; pageSize?: number; search?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.search) query.set('search', params.search);
    return this.request<{ lists: ProblemList[]; pagination: Pagination }>(`/lists?${query.toString()}`);
  }

  async getProblemList(id: number) {
    return this.request<{ list: ProblemList; items: ProblemListEntry[] }>(`/lists/${id}`);
  }

  async createProblemList(data: Record<string, unknown>) {
    return this.request<{ id: number; message: string }>('/lists', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateProblemList(id: number, data: Record<string, unknown>) {
    return this.request<{ message: string }>(`/lists/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteProblemList(id: number) {
    return this.request<{ message: string }>(`/lists/${id}`, {
      method: 'DELETE',
    });
  }

  // Admin - Contests
  async getAdminContests(params?: { page?: number; pageSize?: number }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    return this.request<{ contests: Contest[]; pagination: Pagination }>(`/admin/contests?${query.toString()}`);
  }

  // Admin - Tickets
  async getAdminTickets(params?: { page?: number; pageSize?: number; status?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.status) query.set('status', params.status);
    return this.request<{ tickets: Ticket[]; pagination: Pagination }>(`/admin/tickets?${query.toString()}`);
  }

  // Admin - Problem Lists
  async getAdminLists(params?: { page?: number; pageSize?: number }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    return this.request<{ lists: ProblemList[]; pagination: Pagination }>(`/admin/lists?${query.toString()}`);
  }

  // Admin - SQL Execute (super admin only)
  async executeSql(query: string, password?: string) {
    return this.request<{ results?: Record<string, unknown>[]; meta?: Record<string, unknown> }>(`/admin/sql`, {
      method: 'POST',
      body: JSON.stringify({ query, password }),
    });
  }

  // SQL Visual Editor APIs
  async getSqlTables() {
    return this.request<{ tables: string[] }>('/admin/sql/tables');
  }

  async getTableSchema(tableName: string) {
    return this.request<{ schema: TableColumn[] }>(`/admin/sql/table/${tableName}/schema`);
  }

  async getTableData(tableName: string, params?: { page?: number; pageSize?: number }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    return this.request<{ rows: Record<string, unknown>[]; pagination: Pagination }>(`/admin/sql/table/${tableName}/data?${query.toString()}`);
  }

  async insertTableRow(tableName: string, data: Record<string, unknown>) {
    return this.request<{ meta: Record<string, unknown> }>(`/admin/sql/table/${tableName}/row`, {
      method: 'POST',
      body: JSON.stringify({ data }),
    });
  }

  async updateTableRow(tableName: string, data: Record<string, unknown>, where: Record<string, unknown>) {
    return this.request<{ meta: Record<string, unknown> }>(`/admin/sql/table/${tableName}/row`, {
      method: 'PUT',
      body: JSON.stringify({ data, where }),
    });
  }

  async deleteTableRow(tableName: string, where: Record<string, unknown>, password: string) {
    return this.request<{ meta: Record<string, unknown> }>(`/admin/sql/table/${tableName}/row`, {
      method: 'DELETE',
      body: JSON.stringify({ where, password }),
    });
  }

  // Solutions
  async getSolutions(params?: { problem_id?: number; page?: number; pageSize?: number; sort?: string }) {
    const query = new URLSearchParams();
    if (params?.problem_id) query.set('problem_id', String(params.problem_id));
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.sort) query.set('sort', params.sort);
    return this.request<{ solutions: Solution[]; pagination: Pagination }>(`/solutions?${query.toString()}`);
  }

  async getSolution(id: number) {
    return this.request<{ solution: Solution; is_voted: boolean }>(`/solutions/${id}`);
  }

  async createSolution(data: { problem_id: number; title: string; content: string; language?: string; captcha_uuid?: string; captcha_answer?: string }) {
    return this.request<{ id: number; message: string }>('/solutions', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateSolution(id: number, data: { title?: string; content?: string; language?: string }) {
    return this.request<{ message: string }>(`/solutions/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteSolution(id: number) {
    return this.request<{ message: string }>(`/solutions/${id}`, {
      method: 'DELETE',
    });
  }

  async voteSolution(id: number) {
    return this.request<{ vote_count: number; is_voted: boolean }>(`/solutions/${id}/vote`, {
      method: 'POST',
    });
  }

  // Discussions
  async getDiscussions(params?: { problem_id?: number; page?: number; pageSize?: number; category?: string; sort?: string }) {
    const query = new URLSearchParams();
    if (params?.problem_id) query.set('problem_id', String(params.problem_id));
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.category) query.set('category', params.category);
    if (params?.sort) query.set('sort', params.sort);
    return this.request<{ discussions: Discussion[]; pagination: Pagination }>(`/discussions?${query.toString()}`);
  }

  async getDiscussion(id: number) {
    return this.request<{ discussion: Discussion; replies: DiscussionReply[] }>(`/discussions/${id}`);
  }

  async createDiscussion(data: { problem_id?: number; title: string; content: string; category?: string; captcha_uuid?: string; captcha_answer?: string }) {
    return this.request<{ id: number; message: string }>('/discussions', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateDiscussion(id: number, data: { title?: string; content?: string; category?: string }) {
    return this.request<{ message: string }>(`/discussions/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteDiscussion(id: number) {
    return this.request<{ message: string }>(`/discussions/${id}`, {
      method: 'DELETE',
    });
  }

  async createDiscussionReply(discussionId: number, content: string) {
    return this.request<{ message: string }>(`/discussions/${discussionId}/replies`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
  }

  async deleteDiscussionReply(discussionId: number, replyId: number) {
    return this.request<{ message: string }>(`/discussions/${discussionId}/replies/${replyId}`, {
      method: 'DELETE',
    });
  }

  async updateProfile(data: { avatar_url?: string; bio?: string; signature?: string }) {
    return this.request<{ user: User }>('/users/profile', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async changePassword(oldPassword: string, newPassword: string) {
    return this.request<{ message: string }>('/users/change-password', {
      method: 'PUT',
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
    });
  }

  // Settings
  async getSettings() {
    return this.request<Record<string, string>>('/settings');
  }

  async getSiteStats() {
    return this.request<{ problems: number; users: number; submissions: number; today_submissions: number }>('/settings/stats');
  }

  async getUserHeatmap() {
    return this.request<{ heatmap: Record<string, number> }>('/users/heatmap');
  }

  async getUserLanguageStats() {
    return this.request<{ languages: { language: string; total: number; accepted: number }[] }>('/users/language-stats');
  }

  async getSetting(key: string) {
    return this.request<{ value: string }>(`/settings/${key}`);
  }

  async updateSettings(data: Record<string, string>) {
    return this.request<{ message: string }>('/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async uploadImage(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    return this.request<{ id: number; url: string; filename: string; original_name: string; file_type: string; size_bytes: number }>('/uploads/image', {
      method: 'POST',
      body: formData,
    }, true);
  }

  async uploadFile(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    return this.request<{ id: number; url: string; filename: string; original_name: string; file_type: string; size_bytes: number }>('/uploads/file', {
      method: 'POST',
      body: formData,
    }, true);
  }

  async uploadAvatar(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    return this.request<{ avatar_url: string; message: string }>('/uploads/avatar', {
      method: 'POST',
      body: formData,
    }, true);
  }

  async getUploads(params?: { page?: number; pageSize?: number; type?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.type) query.set('type', params.type);
    return this.request<{ uploads: Upload[]; pagination: Pagination }>(`/uploads?${query.toString()}`);
  }

  async deleteUpload(id: number) {
    return this.request<{ message: string }>(`/uploads/${id}`, {
      method: 'DELETE',
    });
  }

  // AI
  async aiChat(messages: { role: string; content: string }[], context?: string, model?: string) {
    return this.request<{ content: string; model: string; provider: string; tool_calls?: AIToolCall[] }>('/ai/chat', {
      method: 'POST',
      body: JSON.stringify({ messages, context, model }),
    });
  }

  // Streaming AI chat — returns an async generator of SSE events
  async *aiChatStream(
    messages: { role: string; content: string }[],
    context?: string,
    model?: string
  ): AsyncGenerator<{ type: string; data: AIStreamData }> {
    const token = useAuthStore.getState().token;
    const url = `${API_BASE}/ai/chat`;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ messages, context, model, stream: true }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ error: { message: 'Request failed' } }));
      throw new Error(err.error?.message || `HTTP ${response.status}`);
    }

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';
        for (const part of parts) {
          let eventType = '';
          let eventData: Record<string, unknown> = {};
          for (const line of part.split('\n')) {
            if (line.startsWith('event: ')) eventType = line.slice(7).trim();
            else if (line.startsWith('data: ')) {
              try { eventData = JSON.parse(line.slice(6)); } catch { /* keep empty */ }
            }
          }
          if (eventType) yield { type: eventType, data: eventData as AIStreamData };
        }
      }
    } finally {
      reader.releaseLock();
    }
  }

  async aiComplete(data: { code: string; language?: string; problem_title?: string; problem_description?: string; instruction?: string; model?: string }) {
    return this.request<{ content: string; model: string; provider: string }>('/ai/complete', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async aiStatus() {
    return this.request<{ available: boolean; chat_enabled: boolean; completion_enabled: boolean; provider: string; model: string; allowed_models: { model: string; display_name: string }[] }>('/ai/status');
  }

  async getAIModels() {
    return this.request<{ models: AIModelConfig[] }>('/ai/models');
  }

  async updateAIModels(models: AIModelConfig[]) {
    return this.request<{ models: AIModelConfig[] }>('/ai/models', {
      method: 'PUT',
      body: JSON.stringify({ models }),
    });
  }

  // ── Audit Logs ──

  async getAuditLogs(params: {
    page?: number;
    pageSize?: number;
    search?: string;
    action?: string;
    ip?: string;
  } = {}) {
    const query = new URLSearchParams();
    if (params.page) query.set('page', String(params.page));
    if (params.pageSize) query.set('pageSize', String(params.pageSize));
    if (params.search) query.set('search', params.search);
    if (params.action) query.set('action', params.action);
    if (params.ip) query.set('ip', params.ip);
    return this.request<{
      logs: AuditLog[];
      pagination: Pagination;
    }>(`/audit/logs?${query.toString()}`);
  }

  // ── Banned IPs ──

  async getBannedIPs(params: { page?: number; pageSize?: number } = {}) {
    const query = new URLSearchParams();
    if (params.page) query.set('page', String(params.page));
    if (params.pageSize) query.set('pageSize', String(params.pageSize));
    return this.request<{
      bans: BannedIP[];
      pagination: Pagination;
    }>(`/audit/banned-ips?${query.toString()}`);
  }

  async banIP(ip: string, reason: string = '') {
    return this.request<{ message: string }>('/audit/banned-ips', {
      method: 'POST',
      body: JSON.stringify({ ip, reason }),
    });
  }

  async unbanIP(id: number) {
    return this.request<{ message: string }>(`/audit/banned-ips/${id}`, {
      method: 'DELETE',
    });
  }

  // ── Banned Devices ──

  async getBannedDevices(params: { page?: number; pageSize?: number } = {}) {
    const query = new URLSearchParams();
    if (params.page) query.set('page', String(params.page));
    if (params.pageSize) query.set('pageSize', String(params.pageSize));
    return this.request<{
      bans: BannedDevice[];
      pagination: Pagination;
    }>(`/audit/banned-devices?${query.toString()}`);
  }

  async banDevice(device_fingerprint: string, reason: string = '') {
    return this.request<{ message: string }>('/audit/banned-devices', {
      method: 'POST',
      body: JSON.stringify({ device_fingerprint, reason }),
    });
  }

  async unbanDevice(id: number) {
    return this.request<{ message: string }>(`/audit/banned-devices/${id}`, {
      method: 'DELETE',
    });
  }

  // Training plans
  async getTrainingPlans(params?: { page?: number; pageSize?: number; search?: string; category?: string; difficulty?: string; official?: boolean }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.search) query.set('search', params.search);
    if (params?.category) query.set('category', params.category);
    if (params?.difficulty) query.set('difficulty', params.difficulty);
    if (params?.official) query.set('official', '1');
    return this.request<{ plans: TrainingPlan[]; pagination: Pagination }>(`/training?${query.toString()}`);
  }

  async getTrainingPlan(id: number) {
    return this.request<{ plan: TrainingPlan; chapters?: TrainingChapter[] }>(`/training/${id}`);
  }

  async getTrainingProgress(id: number) {
    return this.request<{ completed: number; total: number; percent: number }>(`/training/${id}/progress`);
  }

  async joinTraining(id: number) {
    return this.request<{ message: string }>(`/training/${id}/join`, { method: 'POST' });
  }

  async createTrainingPlan(data: Record<string, unknown>) {
    return this.request<{ id: number; message: string }>('/training', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateTrainingPlan(id: number, data: Record<string, unknown>) {
    return this.request<{ message: string }>(`/training/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteTrainingPlan(id: number) {
    return this.request<{ message: string }>(`/training/${id}`, { method: 'DELETE' });
  }

  async addTrainingChapter(planId: number, data: { title: string; description?: string; sort_order?: number }) {
    return this.request<{ id: number; message: string }>(`/training/${planId}/chapters`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateTrainingChapter(id: number, data: { title?: string; description?: string; sort_order?: number }) {
    return this.request<{ message: string }>(`/training/chapters/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteTrainingChapter(id: number) {
    return this.request<{ message: string }>(`/training/chapters/${id}`, { method: 'DELETE' });
  }

  async addChapterProblem(chapterId: number, data: { problem_id: number; note?: string; sort_order?: number }) {
    return this.request<{ message: string }>(`/training/chapters/${chapterId}/problems`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async removeChapterProblem(chapterId: number, problemId: number) {
    return this.request<{ message: string }>(`/training/chapters/${chapterId}/problems/${problemId}`, {
      method: 'DELETE',
    });
  }

  // Plagiarism
  async triggerPlagiarismCheck(contestId: number) {
    return this.request<{ checked: number; reports: number; message: string }>(`/admin/contests/${contestId}/plagiarism-check`, {
      method: 'POST',
    });
  }

  async getPlagiarismReports(contestId: number) {
    return this.request<{ reports: PlagiarismReport[] }>(`/admin/contests/${contestId}/plagiarism-reports`);
  }

  async getPlagiarismReport(id: number) {
    return this.request<{ report: PlagiarismReport; submission_a: Submission; submission_b: Submission }>(`/admin/plagiarism/${id}`);
  }

  // Notifications
  async getNotifications(params?: { page?: number; pageSize?: number; type?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.type) query.set('type', params.type);
    return this.request<{ notifications: AppNotification[]; pagination: Pagination }>(`/notifications?${query.toString()}`);
  }

  async getUnreadNotificationsCount() {
    return this.request<{ count: number }>('/notifications/unread-count');
  }

  async markNotificationRead(id: number) {
    return this.request<{ message: string }>(`/notifications/${id}/read`, { method: 'POST' });
  }

  async markAllNotificationsRead() {
    return this.request<{ message: string }>('/notifications/read-all', { method: 'POST' });
  }

  async getNotificationPreferences() {
    return this.request<{ preferences: Record<string, string> }>('/notifications/preferences');
  }

  async saveNotificationPreferences(preferences: Record<string, string>) {
    return this.request<{ message: string }>('/notifications/preferences', { method: 'PUT', body: JSON.stringify({ preferences }) });
  }

  // Follows
  async followUser(username: string) {
    return this.request<{ following: boolean; message: string }>(`/users/${username}/follow`, { method: 'POST' });
  }

  async unfollowUser(username: string) {
    return this.request<{ following: boolean; message: string }>(`/users/${username}/follow`, { method: 'DELETE' });
  }

  async getFollowers(username: string, params?: { page?: number; pageSize?: number }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    return this.request<{ users: User[]; pagination: Pagination }>(`/users/${username}/followers?${query.toString()}`);
  }

  async getFollowing(username: string, params?: { page?: number; pageSize?: number }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    return this.request<{ users: User[]; pagination: Pagination }>(`/users/${username}/following?${query.toString()}`);
  }

  // Messages
  async getConversations() {
    return this.request<{ conversations: Conversation[] }>('/messages/conversations');
  }

  async getConversation(id: number, params?: { page?: number; pageSize?: number }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    return this.request<{ messages: Message[]; pagination: Pagination }>(`/messages/conversations/${id}?${query.toString()}`);
  }

  async sendMessage(targetUserId: number, content: string) {
    return this.request<{ conversation_id: number; message: string }>('/messages/conversations', {
      method: 'POST',
      body: JSON.stringify({ target_user_id: targetUserId, content }),
    });
  }

  async markConversationRead(id: number) {
    return this.request<{ message: string }>(`/messages/conversations/${id}/read`, { method: 'POST' });
  }

  async getUnreadMessagesCount() {
    return this.request<{ count: number }>('/messages/unread-count');
  }

  // Teams
  async getTeams(params?: { page?: number; pageSize?: number; search?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.search) query.set('search', params.search);
    return this.request<{ teams: Team[]; pagination: Pagination }>(`/teams?${query.toString()}`);
  }

  async getTeam(slug: string) {
    return this.request<{
      team: Team;
      members: TeamMember[];
      announcements?: TeamAnnouncement[];
      user_membership?: { role: string; joined_at: string };
      join_request?: { id: number; status: string };
      stats?: { member_count: number; problem_count: number; contest_count: number };
    }>(`/teams/${slug}`);
  }

  async createTeam(data: { name: string; slug: string; description?: string; avatar_url?: string; is_public?: boolean }) {
    return this.request<{ id: number; message: string }>('/teams', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateTeam(id: number, data: Record<string, unknown>) {
    return this.request<{ message: string }>(`/teams/${id}`, { method: 'PUT', body: JSON.stringify(data) });
  }

  async deleteTeam(id: number) {
    return this.request<{ message: string }>(`/teams/${id}`, { method: 'DELETE' });
  }

  async joinTeam(id: number) {
    return this.request<{ message: string }>(`/teams/${id}/join`, { method: 'POST', body: '{}' });
  }

  async leaveTeam(id: number) {
    return this.request<{ message: string }>(`/teams/${id}/leave`, { method: 'POST' });
  }

  async removeTeamMember(teamId: number, userId: number) {
    return this.request<{ message: string }>(`/teams/${teamId}/members/${userId}`, { method: 'DELETE' });
  }

  async getTeamRankings(id: number) {
    return this.request<{ rankings: RatingChange[] }>(`/teams/${id}/rankings`);
  }

  async transferTeam(id: number, userId: number) {
    return this.request<{ message: string }>(`/teams/${id}/transfer`, { method: 'POST', body: JSON.stringify({ user_id: userId }) });
  }

  async updateTeamMemberRole(teamId: number, userId: number, role: string) {
    return this.request<{ message: string }>(`/teams/${teamId}/role`, { method: 'PUT', body: JSON.stringify({ user_id: userId, role }) });
  }

  async getTeamMembers(teamId: number) {
    return this.request<{ members: TeamMember[] }>(`/teams/${teamId}/members`);
  }

  async getTeamJoinRequests(teamId: number, status: string = 'pending') {
    return this.request<{ requests: TeamJoinRequest[]; pagination: Pagination }>(`/teams/${teamId}/join-requests?status=${status}`);
  }

  async approveTeamJoinRequest(teamId: number, requestId: number) {
    return this.request<{ message: string }>(`/teams/${teamId}/join-requests/${requestId}`, { method: 'PUT', body: JSON.stringify({ status: 'approved' }) });
  }

  async rejectTeamJoinRequest(teamId: number, requestId: number) {
    return this.request<{ message: string }>(`/teams/${teamId}/join-requests/${requestId}`, { method: 'PUT', body: JSON.stringify({ status: 'rejected' }) });
  }

  // ── Team Announcements ──
  async getTeamAnnouncements(teamId: number, params?: { page?: number; pageSize?: number }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    return this.request<{ announcements: TeamAnnouncement[]; pagination: Pagination }>(`/teams/${teamId}/announcements?${query.toString()}`);
  }

  async createTeamAnnouncement(teamId: number, data: { title: string; content: string; is_pinned?: boolean }) {
    return this.request<{ id: number; message: string }>(`/teams/${teamId}/announcements`, { method: 'POST', body: JSON.stringify(data) });
  }

  async updateTeamAnnouncement(teamId: number, announcementId: number, data: Record<string, unknown>) {
    return this.request<{ message: string }>(`/teams/${teamId}/announcements/${announcementId}`, { method: 'PUT', body: JSON.stringify(data) });
  }

  async deleteTeamAnnouncement(teamId: number, announcementId: number) {
    return this.request<{ message: string }>(`/teams/${teamId}/announcements/${announcementId}`, { method: 'DELETE' });
  }

  // ── Team Discussions ──
  async getTeamDiscussions(teamId: number, params?: { page?: number; pageSize?: number; sort?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.sort) query.set('sort', params.sort);
    return this.request<{ discussions: TeamDiscussion[]; pagination: Pagination }>(`/teams/${teamId}/discussions?${query.toString()}`);
  }

  async createTeamDiscussion(teamId: number, data: { title: string; content: string }) {
    return this.request<{ id: number; message: string }>(`/teams/${teamId}/discussions`, { method: 'POST', body: JSON.stringify(data) });
  }

  async getTeamDiscussion(teamId: number, discussionId: number) {
    return this.request<{ discussion: TeamDiscussion; replies: TeamDiscussionReply[] }>(`/teams/${teamId}/discussions/${discussionId}`);
  }

  async replyTeamDiscussion(teamId: number, discussionId: number, content: string) {
    return this.request<{ message: string }>(`/teams/${teamId}/discussions/${discussionId}/replies`, { method: 'POST', body: JSON.stringify({ content }) });
  }

  async deleteTeamDiscussion(teamId: number, discussionId: number) {
    return this.request<{ message: string }>(`/teams/${teamId}/discussions/${discussionId}`, { method: 'DELETE' });
  }

  // ── Team Problem Sets ──
  async getTeamProblemSets(teamId: number, params?: { page?: number; pageSize?: number }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    return this.request<{ problem_sets: TeamProblemSet[]; pagination: Pagination }>(`/teams/${teamId}/problem-sets?${query.toString()}`);
  }

  async createTeamProblemSet(teamId: number, data: { title: string; description?: string; is_public?: boolean }) {
    return this.request<{ id: number; message: string }>(`/teams/${teamId}/problem-sets`, { method: 'POST', body: JSON.stringify(data) });
  }

  async getTeamProblemSet(teamId: number, setId: number) {
    return this.request<{ problem_set: TeamProblemSet; problems: ProblemListItem[] }>(`/teams/${teamId}/problem-sets/${setId}`);
  }

  async deleteTeamProblemSet(teamId: number, setId: number) {
    return this.request<{ message: string }>(`/teams/${teamId}/problem-sets/${setId}`, { method: 'DELETE' });
  }

  async addTeamProblemSetItem(teamId: number, setId: number, data: { problem_id: number; note?: string; sort_order?: number }) {
    return this.request<{ message: string }>(`/teams/${teamId}/problem-sets/${setId}/items`, { method: 'POST', body: JSON.stringify(data) });
  }

  async removeTeamProblemSetItem(teamId: number, setId: number, itemId: number) {
    return this.request<{ message: string }>(`/teams/${teamId}/problem-sets/${setId}/items/${itemId}`, { method: 'DELETE' });
  }

  // ── Team Contests ──
  async getTeamContests(teamId: number, params?: { page?: number; pageSize?: number; status?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.status) query.set('status', params.status);
    return this.request<{ contests: TeamContest[]; pagination: Pagination }>(`/teams/${teamId}/contests?${query.toString()}`);
  }

  async createTeamContest(teamId: number, data: Record<string, unknown>) {
    return this.request<{ id: number; message: string }>(`/teams/${teamId}/contests`, { method: 'POST', body: JSON.stringify(data) });
  }

  async getTeamContest(teamId: number, contestId: number) {
    return this.request<{ contest: TeamContest; problems: ContestProblem[]; participant_count: number; is_registered: boolean }>(`/teams/${teamId}/contests/${contestId}`);
  }

  async registerTeamContest(teamId: number, contestId: number) {
    return this.request<{ message: string }>(`/teams/${teamId}/contests/${contestId}/register`, { method: 'POST' });
  }

  async getTeamContestRankings(teamId: number, contestId: number) {
    return this.request<{ rankings: ContestRanking[] }>(`/teams/${teamId}/contests/${contestId}/rankings`);
  }

  async addTeamContestProblem(teamId: number, contestId: number, data: { problem_id: number; sort_order?: number; score?: number }) {
    return this.request<{ message: string }>(`/teams/${teamId}/contests/${contestId}/problems`, { method: 'POST', body: JSON.stringify(data) });
  }

  async removeTeamContestProblem(teamId: number, contestId: number, problemId: number) {
    return this.request<{ message: string }>(`/teams/${teamId}/contests/${contestId}/problems/${problemId}`, { method: 'DELETE' });
  }

  // Blogs
  async getBlogs(params?: { page?: number; pageSize?: number; sort?: string; tag?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.sort) query.set('sort', params.sort);
    if (params?.tag) query.set('tag', params.tag);
    return this.request<{ blogs: Blog[]; pagination: Pagination }>(`/blogs?${query.toString()}`);
  }

  async getBlog(id: number) {
    return this.request<{ blog: Blog }>(`/blogs/${id}`);
  }

  async createBlog(data: { title: string; content: string; tags?: string; status?: string; captcha_uuid?: string; captcha_answer?: string }) {
    return this.request<{ id: number; message: string }>('/blogs', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateBlog(id: number, data: Record<string, unknown>) {
    return this.request<{ message: string }>(`/blogs/${id}`, { method: 'PUT', body: JSON.stringify(data) });
  }

  async deleteBlog(id: number) {
    return this.request<{ message: string }>(`/blogs/${id}`, { method: 'DELETE' });
  }

  async likeBlog(id: number) {
    return this.request<{ liked: boolean; message: string }>(`/blogs/${id}/like`, { method: 'POST' });
  }

  async getBlogLikeStatus(id: number) {
    return this.request<{ liked: boolean }>(`/blogs/${id}/like-status`);
  }

  async getBlogComments(id: number, params?: { page?: number; pageSize?: number }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    return this.request<{ comments: BlogComment[]; pagination: Pagination }>(`/blogs/${id}/comments?${query.toString()}`);
  }

  async postBlogComment(id: number, content: string) {
    return this.request<{ id: number; message: string }>(`/blogs/${id}/comments`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
  }

  // Solution review
  async getPendingSolutions(params?: { page?: number; pageSize?: number; status?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.status) query.set('status', params.status);
    return this.request<{ solutions: Solution[]; pagination: Pagination }>(`/solutions/admin/review?${query.toString()}`);
  }

  async approveSolution(id: number) {
    return this.request<{ message: string }>(`/solutions/admin/${id}/approve`, { method: 'POST' });
  }

  async rejectSolution(id: number, reason: string) {
    return this.request<{ message: string }>(`/solutions/admin/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  // Problem reports
  async createProblemReport(problemId: number, type: string, description: string) {
    return this.request<{ id: number; message: string }>(`/problems/${problemId}/reports`, {
      method: 'POST',
      body: JSON.stringify({ type, description }),
    });
  }

  async getProblemReports(params?: { page?: number; pageSize?: number; status?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.status) query.set('status', params.status);
    return this.request<{ reports: ProblemReport[]; pagination: Pagination }>(`/problems/admin/reports?${query.toString()}`);
  }

  async updateProblemReport(id: number, status: string, adminReply: string) {
    return this.request<{ message: string }>(`/problems/admin/reports/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ status, admin_reply: adminReply }),
    });
  }

  // === Wave C: Rating / Contest / Recommendation ===

  // Personalized problem recommendations for the current user
  async getRecommendedProblems(limit = 10) {
    return this.request<{ recommendations: RecommendedProblem[]; user_rating: number; top_tags: string[] }>(
      `/problems/recommend?limit=${limit}`
    );
  }

  // Start a virtual participation for an ended contest
  async startVirtualParticipation(contestId: number) {
    return this.request<{ participant_id: number; virtual_start_time: string; message: string }>(
      `/contests/${contestId}/virtual-register`,
      { method: 'POST' }
    );
  }

  // Finalize ratings for a rated contest (admin)
  async finalizeContestRatings(contestId: number) {
    return this.request<{ message: string; changes_count: number; changes: RatingChange[] }>(
      `/contests/${contestId}/finalize`,
      { method: 'POST' }
    );
  }

  // Get rating changes for a finalized contest
  async getContestRatingChanges(contestId: number) {
    return this.request<{ contest: Contest; changes: RatingChange[] }>(`/contests/${contestId}/rating-changes`);
  }

  // ─────────────────────────────────────────────────────────────
  // Admin: Blog management
  // ─────────────────────────────────────────────────────────────
  async getAdminBlogs(params?: { page?: number; pageSize?: number; search?: string; status?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.search) query.set('search', params.search);
    if (params?.status) query.set('status', params.status);
    return this.request<{ blogs: Blog[]; pagination: Pagination }>(`/admin/blogs?${query.toString()}`);
  }

  async getAdminBlog(id: number) {
    return this.request<{ blog: Blog }>(`/admin/blogs/${id}`);
  }

  async updateBlogStatus(id: number, status: string) {
    return this.request<{ message: string }>(`/admin/blogs/${id}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    });
  }

  async deleteBlogAdmin(id: number) {
    return this.request<{ message: string }>(`/admin/blogs/${id}`, { method: 'DELETE' });
  }

  // ─────────────────────────────────────────────────────────────
  // Admin: Team management
  // ─────────────────────────────────────────────────────────────
  async getAdminTeams(params?: { page?: number; pageSize?: number; search?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.search) query.set('search', params.search);
    return this.request<{ teams: Team[]; pagination: Pagination }>(`/admin/teams?${query.toString()}`);
  }

  async deleteTeamAdmin(id: number) {
    return this.request<{ message: string }>(`/admin/teams/${id}`, { method: 'DELETE' });
  }

  async updateTeamVisibility(id: number, isPublic: boolean) {
    return this.request<{ message: string }>(`/admin/teams/${id}/visibility`, {
      method: 'PUT',
      body: JSON.stringify({ is_public: isPublic }),
    });
  }

  // ─────────────────────────────────────────────────────────────
  // Admin: Message moderation
  // ─────────────────────────────────────────────────────────────
  async getAdminConversations(params?: { page?: number; pageSize?: number; search?: string }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.search) query.set('search', params.search);
    return this.request<{ conversations: Conversation[]; pagination: Pagination }>(`/admin/messages/conversations?${query.toString()}`);
  }

  async getAdminConversationMessages(id: number, params?: { page?: number; pageSize?: number }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    return this.request<{ messages: Message[]; pagination: Pagination }>(`/admin/messages/conversations/${id}?${query.toString()}`);
  }

  async deleteMessageAdmin(id: number) {
    return this.request<{ message: string }>(`/admin/messages/${id}`, { method: 'DELETE' });
  }

  async deleteConversationAdmin(id: number) {
    return this.request<{ message: string }>(`/admin/messages/conversations/${id}`, { method: 'DELETE' });
  }

  async sendSystemAnnouncement(title: string, content: string, link?: string) {
    return this.request<{ message: string; sent: number }>(`/admin/announcement/send`, { method: 'POST', body: JSON.stringify({ title, content, link }) });
  }

  // ── Problem Notes ──
  async getNotes(params?: { page?: number; pageSize?: number }) {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    return this.request<{ notes: ProblemNote[]; pagination: Pagination }>(`/notes?${query.toString()}`);
  }

  async getNote(problemId: number) {
    return this.request<{ note: ProblemNote }>(`/notes/${problemId}`);
  }

  async saveNote(problemId: number, content: string, is_public = false) {
    return this.request<{ message: string }>(`/notes/${problemId}`, { method: 'PUT', body: JSON.stringify({ content, is_public }) });
  }

  async deleteNote(problemId: number) {
    return this.request<{ message: string }>(`/notes/${problemId}`, { method: 'DELETE' });
  }

  // ── Achievements ──
  async getAchievements() {
    return this.request<{ achievements: Achievement[] }>(`/achievements`);
  }

  async checkAchievements() {
    return this.request<{ new_achievements: Achievement[]; solved_count: number }>(`/achievements/check`);
  }

  // ── Search ──
  async search(q: string, type: string = 'all') {
    return this.request<{ results: SearchResult[]; total: number; query: string }>(`/search?q=${encodeURIComponent(q)}&type=${type}`);
  }

  // ── Code Templates ──
  async getTemplates() {
    return this.request<{ templates: CodeTemplate[] }>(`/templates`);
  }

  async getTemplate(language: string) {
    return this.request<{ template: CodeTemplate }>(`/templates/${language}`);
  }

  async saveTemplate(language: string, content: string, name?: string) {
    return this.request<{ message: string }>(`/templates/${language}`, { method: 'PUT', body: JSON.stringify({ content, name }) });
  }

  async deleteTemplate(language: string) {
    return this.request<{ message: string }>(`/templates/${language}`, { method: 'DELETE' });
  }

  // ── User Settings ──
  async getUserSettings() {
    return this.request<{ settings: Record<string, string> }>(`/user/settings`);
  }

  async saveUserSettings(settings: Record<string, string>) {
    return this.request<{ message: string }>(`/user/settings`, { method: 'PUT', body: JSON.stringify({ settings }) });
  }

  // ── Search ──
  async searchSuggestions(q: string) {
    return this.request<{ suggestions: SearchSuggestion[] }>(`/search/suggestions?q=${encodeURIComponent(q)}`);
  }

  // ── Auth: Password Reset ──
  async forgotPassword(email: string) {
    return this.request<{ message: string; resetUrl?: string }>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  }

  async resetPassword(token: string, password: string) {
    return this.request<{ message: string }>('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ token, password }),
    });
  }
}

export const api = new ApiClient(API_BASE);

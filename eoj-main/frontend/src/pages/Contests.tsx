import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';
import { Trophy, Calendar, Users, Filter, PlusCircle, AlertCircle } from 'lucide-react';
import { t } from '../i18n';
import { usePermissions } from '../hooks/usePermissions';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { useNow } from '../hooks/useNow';
import './Contests.css';

const STATUS_OPTIONS = ['all', 'upcoming', 'running', 'ended'] as const;

const STATUS_BADGE_CLASS: Record<string, string> = {
  upcoming: 'badge badge-info',
  running: 'badge badge-success',
  ended: 'badge badge-ended',
};

export default function Contests() {
  const perms = usePermissions();
  const [contests, setContests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const now = useNow();
  useDocumentTitle(t('contests.title'));

  const fetchContests = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const data = await api.getContests({
        status: statusFilter !== 'all' ? statusFilter : undefined,
      });
      setContests(data.contests);
    } catch (e) {
      console.error('Failed to fetch contests:', e);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchContests();
  }, [fetchContests]);

  const getStatusLabel = (status: string) => {
    if (status === 'upcoming') return t('contests.upcoming');
    if (status === 'running') return t('contests.running');
    return t('contests.ended');
  };

  const getContestStatus = (contest: any): string => {
    if (contest.status) return contest.status;
    const start = new Date(contest.start_time).getTime();
    const end = new Date(contest.end_time).getTime();
    if (now < start) return 'upcoming';
    if (now >= start && now <= end) return 'running';
    return 'ended';
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString();
  };

  return (
    <div className="contests-page">
      <div className="contests-header">
        <div className="contests-title-section">
          <Trophy size={28} className="title-icon" />
          <div>
            <h1 className="page-title">{t('contests.title')}</h1>
          </div>
        </div>

        {perms.canManageContests && (
          <Link to="/contests/new" className="btn btn-primary btn-sm">
            <PlusCircle size={14} />
            {t('contests.createContest')}
          </Link>
        )}

        <div className="status-filter">
          <Filter size={14} />
          {STATUS_OPTIONS.map((status) => (
            <button
              key={status}
              className={`filter-btn ${statusFilter === status ? 'active' : ''}`}
              onClick={() => setStatusFilter(status)}
            >
              {status === 'all' ? t('contests.all') : getStatusLabel(status)}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <LoadingSpinner />
      ) : loadError ? (
        <div className="error-banner">
          <AlertCircle size={16} />
          <span>{t('common.loadError')}</span>
          <button className="btn btn-secondary btn-sm" onClick={fetchContests}>{t('common.retry')}</button>
        </div>
      ) : contests.length === 0 ? (
        <EmptyState
          icon={Trophy}
          title={t('contests.noContests')}
        />
      ) : (
        <div className="contests-list">
          {contests.map((contest) => {
            const status = getContestStatus(contest);
            return (
              <Link
                key={contest.id}
                to={`/contests/${contest.id}`}
                className="contest-card"
              >
                <div className="contest-card-header">
                  <h3 className="contest-title">{contest.title}</h3>
                  <span className={STATUS_BADGE_CLASS[status] || 'badge'}>
                    {getStatusLabel(status)}
                  </span>
                </div>
                <div className="contest-card-body">
                  <div className="contest-info-row">
                    <Calendar size={14} />
                    <span className="contest-time">
                      {t('contests.startTime')}: {formatDate(contest.start_time)}
                    </span>
                    <span className="contest-time-separator">→</span>
                    <span className="contest-time">
                      {t('contests.endTime')}: {formatDate(contest.end_time)}
                    </span>
                  </div>
                  <div className="contest-info-row">
                    <Users size={14} />
                    <span>{t('contests.participants')}: {contest.participant_count ?? 0}</span>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

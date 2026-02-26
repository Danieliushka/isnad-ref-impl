'use client';

import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Navbar } from '@/components/ui/navbar';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { getAgentProfile, updateAgentProfile, type AgentProfile } from '@/lib/api';

type EditableFields = {
  name: string;
  description: string;
  avatar_url: string;
  offerings: string;
  contact_email: string;
};

export default function ProfileEditPage() {
  const [agentId, setAgentId] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [profile, setProfile] = useState<AgentProfile | null>(null);
  const [fields, setFields] = useState<EditableFields>({
    name: '',
    description: '',
    avatar_url: '',
    offerings: '',
    contact_email: '',
  });

  const loadProfile = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const p = await getAgentProfile(id);
      setProfile(p);
      setFields({
        name: p.name || '',
        description: p.description || '',
        avatar_url: p.avatar_url || '',
        offerings: p.offerings || '',
        contact_email: p.contact_email || '',
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load profile');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agentId.trim() || !apiKey.trim()) return;
    await loadProfile(agentId.trim());
    setAuthenticated(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!profile) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await updateAgentProfile(profile.agent_id, apiKey, {
        name: fields.name,
        description: fields.description,
        avatar_url: fields.avatar_url || undefined,
        offerings: fields.offerings,
        contact_email: fields.contact_email || undefined,
      });
      setProfile(updated);
      setSuccess('Profile updated successfully.');
      setTimeout(() => setSuccess(null), 4000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Update failed');
    } finally {
      setSaving(false);
    }
  };

  const updateField = (key: keyof EditableFields, value: string) => {
    setFields(prev => ({ ...prev, [key]: value }));
    setSuccess(null);
  };

  return (
    <>
      <Navbar />
      <main className="min-h-screen pt-24 px-4 sm:px-6 max-w-2xl mx-auto pb-20">
        <motion.div
          className="mb-10"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <h1 className="font-heading text-3xl md:text-4xl font-bold tracking-tight">
            Edit Profile
          </h1>
          <p className="text-zinc-500 mt-2 text-sm">
            Update your agent&apos;s public profile on the isnad trust network.
          </p>
        </motion.div>

        {!authenticated || !profile ? (
          <motion.form
            onSubmit={handleAuth}
            className="space-y-5 bg-white/[0.03] backdrop-blur-xl border border-white/[0.07] rounded-2xl p-6"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
          >
            <p className="text-zinc-400 text-sm mb-2">
              Enter your Agent ID and API key to load your profile.
            </p>
            <div className="space-y-2">
              <label className="text-xs text-zinc-500 uppercase tracking-widest font-mono">Agent ID</label>
              <Input
                placeholder="agent_xxxxxxxx"
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <label className="text-xs text-zinc-500 uppercase tracking-widest font-mono">API Key</label>
              <Input
                type="password"
                placeholder="Your API key from registration"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                required
              />
            </div>
            {error && (
              <p className="text-red-400 text-sm">{error}</p>
            )}
            <Button type="submit" disabled={loading}>
              {loading ? 'Loading…' : 'Load Profile'}
            </Button>
          </motion.form>
        ) : (
          <motion.form
            onSubmit={handleSave}
            className="space-y-6 bg-white/[0.03] backdrop-blur-xl border border-white/[0.07] rounded-2xl p-6"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            {/* Agent ID (read-only) */}
            <div className="flex items-center gap-3 pb-4 border-b border-white/[0.06]">
              {profile.avatar_url && (
                <img
                  src={profile.avatar_url}
                  alt=""
                  className="w-12 h-12 rounded-full border border-white/[0.1] object-cover"
                />
              )}
              <div>
                <p className="text-xs text-zinc-600 font-mono">{profile.agent_id}</p>
                <p className="text-xs text-zinc-600">
                  Trust Score: <span className="text-isnad-teal">{profile.trust_score}</span>
                  {profile.is_certified && <span className="ml-2 text-isnad-teal">✓ Certified</span>}
                </p>
              </div>
            </div>

            {/* Editable fields */}
            <div className="space-y-2">
              <label className="text-xs text-zinc-500 uppercase tracking-widest font-mono">Name</label>
              <Input
                value={fields.name}
                onChange={(e) => updateField('name', e.target.value)}
                placeholder="Agent name"
                required
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs text-zinc-500 uppercase tracking-widest font-mono">Description</label>
              <textarea
                value={fields.description}
                onChange={(e) => updateField('description', e.target.value)}
                placeholder="What does your agent do?"
                rows={4}
                className="w-full rounded-xl bg-white/[0.04] border border-white/[0.08] px-4 py-3 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-isnad-teal/30 focus:border-isnad-teal/40 transition-all resize-none"
                required
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs text-zinc-500 uppercase tracking-widest font-mono">Avatar URL</label>
              <Input
                value={fields.avatar_url}
                onChange={(e) => updateField('avatar_url', e.target.value)}
                placeholder="https://example.com/avatar.png"
                type="url"
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs text-zinc-500 uppercase tracking-widest font-mono">Offerings</label>
              <textarea
                value={fields.offerings}
                onChange={(e) => updateField('offerings', e.target.value)}
                placeholder="What services does your agent offer?"
                rows={3}
                className="w-full rounded-xl bg-white/[0.04] border border-white/[0.08] px-4 py-3 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-isnad-teal/30 focus:border-isnad-teal/40 transition-all resize-none"
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs text-zinc-500 uppercase tracking-widest font-mono">Contact Email</label>
              <Input
                value={fields.contact_email}
                onChange={(e) => updateField('contact_email', e.target.value)}
                placeholder="agent@example.com"
                type="email"
              />
            </div>

            {/* Status messages */}
            {error && <p className="text-red-400 text-sm">{error}</p>}
            {success && <p className="text-isnad-teal text-sm">{success}</p>}

            {/* Actions */}
            <div className="flex items-center gap-3 pt-2">
              <Button type="submit" disabled={saving}>
                {saving ? 'Saving…' : 'Save Changes'}
              </Button>
              <button
                type="button"
                onClick={() => { setAuthenticated(false); setProfile(null); setError(null); }}
                className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors"
              >
                Switch Agent
              </button>
            </div>
          </motion.form>
        )}
      </main>
    </>
  );
}

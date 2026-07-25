import { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import AppShell from '@/components/AppShell';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Zap, Mail, FileText, Clock, AlertCircle, StopCircle } from 'lucide-react';

export default function AppAutomations() {
  const { user } = useAuth();

  return (
    <AppShell>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Automations</h1>
            <p className="text-sm text-slate-500">Evidence-based outreach drafts and workflow automation</p>
          </div>
          <Badge variant="outline" className="text-xs border-green-200 text-green-700 bg-green-50">
            Draft-Only Mode
          </Badge>
        </div>

        <Tabs defaultValue="outreach" className="space-y-4">
          <TabsList className="bg-slate-100">
            <TabsTrigger value="outreach">Outreach Drafts</TabsTrigger>
            <TabsTrigger value="queues">Queues</TabsTrigger>
            <TabsTrigger value="logs">Activity Log</TabsTrigger>
          </TabsList>

          <TabsContent value="outreach" className="space-y-4">
            <Card className="border-slate-200">
              <CardContent className="p-6">
                <div className="flex items-start gap-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 shrink-0">
                    <Mail className="h-5 w-5 text-indigo-600" />
                  </div>
                  <div>
                    <h3 className="font-medium text-slate-900">Evidence-Based Outreach</h3>
                    <p className="text-sm text-slate-500 mt-1">
                      Generate personalized email drafts that cite specific evidence from lead audits. 
                      All messages require human review before sending.
                    </p>
                    <div className="mt-4 space-y-2">
                      <div className="flex items-center gap-2 text-xs text-slate-600">
                        <AlertCircle className="h-3.5 w-3.5 text-amber-500" />
                        <span>Sender integration required — connect Gmail or SMTP in Settings → Integrations</span>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-slate-600">
                        <StopCircle className="h-3.5 w-3.5 text-green-500" />
                        <span>Emergency stop available · Suppression lists enforced · Draft-only by default</span>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-slate-200 border-dashed">
              <CardContent className="p-8 text-center">
                <Zap className="h-8 w-8 text-slate-300 mx-auto mb-3" />
                <h3 className="font-medium text-slate-700">Outreach requires sender connection</h3>
                <p className="text-sm text-slate-500 mt-1 max-w-md mx-auto">
                  Connect a verified sender (Gmail, Outlook, or SMTP) in Settings → Integrations 
                  to generate and send evidence-based outreach drafts.
                </p>
                <Button variant="outline" size="sm" className="mt-4 border-slate-200" onClick={() => window.location.href = '/app/settings/workspace'}>
                  Configure Integrations
                </Button>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="queues" className="space-y-4">
            <Card className="border-slate-200">
              <CardContent className="p-6">
                <div className="flex items-start gap-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-50 shrink-0">
                    <Clock className="h-5 w-5 text-purple-600" />
                  </div>
                  <div>
                    <h3 className="font-medium text-slate-900">Automation Queues</h3>
                    <p className="text-sm text-slate-500 mt-1">
                      Schedule and manage outreach sequences with quiet hours, per-domain caps, 
                      daily limits, and pause/resume controls.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
            <div className="flex flex-col items-center py-8 text-center">
              <p className="text-sm text-slate-500">No active automation queues</p>
            </div>
          </TabsContent>

          <TabsContent value="logs" className="space-y-4">
            <Card className="border-slate-200">
              <CardContent className="p-6">
                <div className="flex items-start gap-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100 shrink-0">
                    <FileText className="h-5 w-5 text-slate-600" />
                  </div>
                  <div>
                    <h3 className="font-medium text-slate-900">Activity Log</h3>
                    <p className="text-sm text-slate-500 mt-1">
                      Full audit trail of all automation actions with timestamps, 
                      success/failure reasons, and credit usage.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
            <div className="flex flex-col items-center py-8 text-center">
              <p className="text-sm text-slate-500">No automation activity yet</p>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
}
import React, { useState } from 'react';
import { Menu, MenuItem, Typography } from '@mui/material';
import HistoryIcon from '@mui/icons-material/History';
import { TooltippedIconButton } from './mui-extras/tooltipped-icon-button';
import { AiService } from '../handler';

export function ChatSessions(): JSX.Element {
  const [sessionsAnchorEl, setSessionsAnchorEl] = useState<null | HTMLElement>(
    null
  );
  const [chatSessions, setChatSessions] = useState<AiService.ChatSessionItem[]>(
    []
  );
  const [loadingSessions, setLoadingSessions] = useState(false);

  const isSessionsOpen = Boolean(sessionsAnchorEl);

  const handleSessionsClick = async (event: React.MouseEvent<HTMLElement>) => {
    setSessionsAnchorEl(event.currentTarget);

    // Load chat history when opening dropdown
    if (!loadingSessions) {
      setLoadingSessions(true);
      try {
        const sessions = await AiService.getChatSessionsList();
        setChatSessions(sessions);
      } catch (error) {
        console.error('Error loading chat history:', error);
      } finally {
        setLoadingSessions(false);
      }
    }
  };

  const handleSessionsClose = () => {
    setSessionsAnchorEl(null);
  };

  const handleChatSelect = async (chatId: string) => {
    try {
      await AiService.updateChatSession(chatId);
      handleSessionsClose();
    } catch (error) {
      console.error('Error loading chat:', error);
    }
  };

  const formatDate = (dateString: string) => {
    try {
      return new Date(dateString).toLocaleDateString();
    } catch {
      return dateString;
    }
  };

  return (
    <>
      <TooltippedIconButton
        onClick={handleSessionsClick}
        tooltip="Chat sessions"
      >
        <HistoryIcon />
      </TooltippedIconButton>

      {/* Chat History Dropdown */}
      <Menu
        anchorEl={sessionsAnchorEl}
        open={isSessionsOpen}
        onClose={handleSessionsClose}
        PaperProps={{
          style: {
            maxHeight: 400,
            width: 300
          }
        }}
      >
        {loadingSessions ? (
          <MenuItem disabled>
            <Typography variant="body2">Loading...</Typography>
          </MenuItem>
        ) : chatSessions.length === 0 ? (
          <MenuItem disabled>
            <Typography variant="body2" color="text.secondary">
              No saved chats found
            </Typography>
          </MenuItem>
        ) : (
          chatSessions.slice(0, 10).map(session => (
            <MenuItem
              key={session.id}
              onClick={() => handleChatSelect(session.id)}
              sx={{
                flexDirection: 'column',
                alignItems: 'flex-start',
                minHeight: 60,
                py: 1.5
              }}
            >
              <Typography
                variant="subtitle2"
                noWrap
                sx={{ width: '100%', fontWeight: 'medium' }}
              >
                {session.title}
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ mt: 0.5 }}
              >
                {formatDate(session.created_at)} messages
              </Typography>
            </MenuItem>
          ))
        )}
      </Menu>
    </>
  );
}

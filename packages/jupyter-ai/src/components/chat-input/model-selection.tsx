import React, { useCallback, useEffect, useState } from 'react';
import {
  Chip,
  ListItemText,
  Menu,
  MenuItem,
  Typography,
  Box,
  CircularProgress
} from '@mui/material';
import Check from '@mui/icons-material/Check';
import KeyboardArrowDown from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUp from '@mui/icons-material/KeyboardArrowUp';
import { DEFAULT_MODEL_OPTIONS, ModelOption } from './model-config';
import { AiService } from '../../handler';
import { useStackingAlert } from '../mui-extras/stacking-alert';

export type ModelSelectionProps = {};

export function ModelSelection(props: ModelSelectionProps): JSX.Element {
  // Alert for showing error messages to user
  const alert = useStackingAlert();

  const [selectedModel, setSelectedModel] = useState<ModelOption>(
    DEFAULT_MODEL_OPTIONS[0]
  );
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [isUpdating, setIsUpdating] = useState<boolean>(false);

  /**
   * Effect: load current completion model configuration on mount
   */
  useEffect(() => {
    async function loadCurrentCompletionModel() {
      try {
        const config = await AiService.getConfig();
        if (config.model_provider_id) {
          const mid = config.model_provider_id?.split(':')[1];
          const model =
            DEFAULT_MODEL_OPTIONS.find(m => m.llm === mid) ??
            DEFAULT_MODEL_OPTIONS[0];
          setSelectedModel(model);
        }
      } catch (error) {
        console.error('Failed to load current completion model:', error);
      }
    }
    loadCurrentCompletionModel();
  }, []);

  /**
   * Handles model selection with optimistic UI updates and automatic rollback on failure
   * Updates both UI state and backend configuration
   */
  const handleModelSelection = useCallback(
    async (model: ModelOption) => {
      setIsUpdating(true);
      const previousModel = selectedModel;
      setSelectedModel(model);
      setAnchor(null);

      try {
        // Update backend configuration
        const currentConfig = await AiService.getConfig();
        const lmGlobalId = `openai-chat-custom:${model.llm}`;
        const updateRequest: AiService.UpdateConfigRequest = {
          model_provider_id: lmGlobalId,
          fields: lmGlobalId
            ? {
                [lmGlobalId]: {
                  openai_api_base: 'https://api.portkey.ai/v1'
                }
              }
            : {},
          last_read: currentConfig.last_read
        };

        await AiService.updateConfig(updateRequest);
        console.info(
          `✅ Updated completion model to: ${model.llm}`,
          updateRequest
        );
      } catch (error) {
        console.error('❌ Failed to update completion model:', error);
        setSelectedModel(previousModel);
        const errorMessage =
          error instanceof Error
            ? error.message
            : 'Failed to update model configuration. Please try again.';
        alert.show('error', errorMessage);
      } finally {
        setIsUpdating(false);
      }
    },
    [selectedModel, alert]
  );

  return (
    <>
      <Chip
        clickable
        onClick={(event: React.MouseEvent<HTMLElement>) => {
          setAnchor(event.currentTarget as HTMLElement);
        }}
        variant="outlined"
        size="small"
        disabled={isUpdating}
        label={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body2" sx={{ lineHeight: 1 }}>
              {selectedModel?.label ?? 'Select model'}
            </Typography>
            {isUpdating ? (
              <CircularProgress size={14} />
            ) : anchor ? (
              <KeyboardArrowUp fontSize="small" />
            ) : (
              <KeyboardArrowDown fontSize="small" />
            )}
          </Box>
        }
        sx={{
          p: '0 2px 0'
        }}
      />

      <Menu
        open={!!anchor}
        onClose={() => setAnchor(null)}
        anchorEl={anchor}
        anchorOrigin={{ vertical: 'top', horizontal: 'left' }}
        transformOrigin={{ vertical: 'bottom', horizontal: 'left' }}
        PaperProps={{
          sx: {
            border: '1px solid #e0e0e0',
            boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
            borderRadius: 4
          }
        }}
      >
        {DEFAULT_MODEL_OPTIONS.map(opt => {
          const isSelected = opt.llm === selectedModel.llm;
          return (
            <MenuItem
              key={opt.llm}
              onClick={() => handleModelSelection(opt)}
              disabled={isUpdating}
            >
              <ListItemText>{opt.label}</ListItemText>
              {isSelected && <Check fontSize="small" />}
            </MenuItem>
          );
        })}
      </Menu>
      {alert.jsx}
    </>
  );
}

export default ModelSelection;
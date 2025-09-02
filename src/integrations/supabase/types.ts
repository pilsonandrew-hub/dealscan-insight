export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "13.0.4"
  }
  public: {
    Tables: {
      canary_tests: {
        Row: {
          created_at: string | null
          expected_fields: Json
          id: string
          last_run: string | null
          pass_rate: number | null
          site_name: string
          test_url: string
          updated_at: string | null
        }
        Insert: {
          created_at?: string | null
          expected_fields: Json
          id?: string
          last_run?: string | null
          pass_rate?: number | null
          site_name: string
          test_url: string
          updated_at?: string | null
        }
        Update: {
          created_at?: string | null
          expected_fields?: Json
          id?: string
          last_run?: string | null
          pass_rate?: number | null
          site_name?: string
          test_url?: string
          updated_at?: string | null
        }
        Relationships: []
      }
      dealer_sales: {
        Row: {
          auction_house: string | null
          condition_grade: string | null
          created_at: string
          id: string
          location: string | null
          make: string
          metadata: Json | null
          mileage: number | null
          model: string
          sale_date: string | null
          sale_price: number
          source_type: string | null
          state: string | null
          title_status: string | null
          trim: string | null
          updated_at: string
          user_id: string | null
          vin: string | null
          year: number
        }
        Insert: {
          auction_house?: string | null
          condition_grade?: string | null
          created_at?: string
          id?: string
          location?: string | null
          make: string
          metadata?: Json | null
          mileage?: number | null
          model: string
          sale_date?: string | null
          sale_price: number
          source_type?: string | null
          state?: string | null
          title_status?: string | null
          trim?: string | null
          updated_at?: string
          user_id?: string | null
          vin?: string | null
          year: number
        }
        Update: {
          auction_house?: string | null
          condition_grade?: string | null
          created_at?: string
          id?: string
          location?: string | null
          make?: string
          metadata?: Json | null
          mileage?: number | null
          model?: string
          sale_date?: string | null
          sale_price?: number
          source_type?: string | null
          state?: string | null
          title_status?: string | null
          trim?: string | null
          updated_at?: string
          user_id?: string | null
          vin?: string | null
          year?: number
        }
        Relationships: []
      }
      error_reports: {
        Row: {
          category: string
          context: Json | null
          created_at: string | null
          error_id: string
          id: string
          message: string
          resolved: boolean | null
          severity: string
          stack_trace: string | null
          timestamp: string
          updated_at: string | null
          user_message: string
        }
        Insert: {
          category: string
          context?: Json | null
          created_at?: string | null
          error_id: string
          id?: string
          message: string
          resolved?: boolean | null
          severity: string
          stack_trace?: string | null
          timestamp: string
          updated_at?: string | null
          user_message: string
        }
        Update: {
          category?: string
          context?: Json | null
          created_at?: string | null
          error_id?: string
          id?: string
          message?: string
          resolved?: boolean | null
          severity?: string
          stack_trace?: string | null
          timestamp?: string
          updated_at?: string | null
          user_message?: string
        }
        Relationships: []
      }
      extraction_strategies: {
        Row: {
          cluster_id: string | null
          confidence_threshold: number | null
          created_at: string | null
          fallback_order: number
          field_name: string
          id: string
          llm_config: Json | null
          ml_config: Json | null
          selector_config: Json | null
          site_name: string
          strategy: string
          success_rate: number | null
          updated_at: string | null
        }
        Insert: {
          cluster_id?: string | null
          confidence_threshold?: number | null
          created_at?: string | null
          fallback_order: number
          field_name: string
          id?: string
          llm_config?: Json | null
          ml_config?: Json | null
          selector_config?: Json | null
          site_name: string
          strategy: string
          success_rate?: number | null
          updated_at?: string | null
        }
        Update: {
          cluster_id?: string | null
          confidence_threshold?: number | null
          created_at?: string | null
          fallback_order?: number
          field_name?: string
          id?: string
          llm_config?: Json | null
          ml_config?: Json | null
          selector_config?: Json | null
          site_name?: string
          strategy?: string
          success_rate?: number | null
          updated_at?: string | null
        }
        Relationships: []
      }
      field_provenance: {
        Row: {
          confidence_score: number | null
          created_at: string
          error_count: number | null
          extraction_method: string
          field_name: string
          id: string
          last_validated: string | null
          metadata: Json | null
          source_table: string
          updated_at: string
          validation_count: number | null
        }
        Insert: {
          confidence_score?: number | null
          created_at?: string
          error_count?: number | null
          extraction_method: string
          field_name: string
          id?: string
          last_validated?: string | null
          metadata?: Json | null
          source_table: string
          updated_at?: string
          validation_count?: number | null
        }
        Update: {
          confidence_score?: number | null
          created_at?: string
          error_count?: number | null
          extraction_method?: string
          field_name?: string
          id?: string
          last_validated?: string | null
          metadata?: Json | null
          source_table?: string
          updated_at?: string
          validation_count?: number | null
        }
        Relationships: []
      }
      health_checks: {
        Row: {
          created_at: string | null
          details: Json | null
          id: string
          response_time_ms: number | null
          service_name: string
          status: string
          timestamp: string | null
        }
        Insert: {
          created_at?: string | null
          details?: Json | null
          id?: string
          response_time_ms?: number | null
          service_name: string
          status: string
          timestamp?: string | null
        }
        Update: {
          created_at?: string | null
          details?: Json | null
          id?: string
          response_time_ms?: number | null
          service_name?: string
          status?: string
          timestamp?: string | null
        }
        Relationships: []
      }
      labels: {
        Row: {
          cluster_id: string | null
          created_at: string | null
          css_path: string | null
          field: string
          id: string
          new_value: string
          old_value: string | null
          updated_at: string | null
          url: string
          user_id: string | null
        }
        Insert: {
          cluster_id?: string | null
          created_at?: string | null
          css_path?: string | null
          field: string
          id?: string
          new_value: string
          old_value?: string | null
          updated_at?: string | null
          url: string
          user_id?: string | null
        }
        Update: {
          cluster_id?: string | null
          created_at?: string | null
          css_path?: string | null
          field?: string
          id?: string
          new_value?: string
          old_value?: string | null
          updated_at?: string | null
          url?: string
          user_id?: string | null
        }
        Relationships: []
      }
      market_prices: {
        Row: {
          avg_price: number
          created_at: string
          expires_at: string
          high_price: number
          id: string
          last_updated: string
          low_price: number
          make: string
          metadata: Json | null
          model: string
          sample_size: number | null
          source_api: string
          state: string | null
          trim: string | null
          user_id: string | null
          year: number
        }
        Insert: {
          avg_price: number
          created_at?: string
          expires_at?: string
          high_price: number
          id?: string
          last_updated?: string
          low_price: number
          make: string
          metadata?: Json | null
          model: string
          sample_size?: number | null
          source_api: string
          state?: string | null
          trim?: string | null
          user_id?: string | null
          year: number
        }
        Update: {
          avg_price?: number
          created_at?: string
          expires_at?: string
          high_price?: number
          id?: string
          last_updated?: string
          low_price?: number
          make?: string
          metadata?: Json | null
          model?: string
          sample_size?: number | null
          source_api?: string
          state?: string | null
          trim?: string | null
          user_id?: string | null
          year?: number
        }
        Relationships: []
      }
      ml_models: {
        Row: {
          accuracy: number | null
          created_at: string
          deployed_at: string | null
          features_used: string[] | null
          hyperparameters: Json | null
          id: string
          metadata: Json | null
          model_type: string
          name: string
          status: string
          training_data_size: number | null
          updated_at: string
          version: string
        }
        Insert: {
          accuracy?: number | null
          created_at?: string
          deployed_at?: string | null
          features_used?: string[] | null
          hyperparameters?: Json | null
          id?: string
          metadata?: Json | null
          model_type: string
          name: string
          status?: string
          training_data_size?: number | null
          updated_at?: string
          version: string
        }
        Update: {
          accuracy?: number | null
          created_at?: string
          deployed_at?: string | null
          features_used?: string[] | null
          hyperparameters?: Json | null
          id?: string
          metadata?: Json | null
          model_type?: string
          name?: string
          status?: string
          training_data_size?: number | null
          updated_at?: string
          version?: string
        }
        Relationships: []
      }
      model_performance_metrics: {
        Row: {
          created_at: string
          dataset_size: number | null
          evaluated_at: string
          id: string
          metadata: Json | null
          metric_type: string
          metric_value: number
          model_name: string
          model_version: string
          test_split: number | null
        }
        Insert: {
          created_at?: string
          dataset_size?: number | null
          evaluated_at?: string
          id?: string
          metadata?: Json | null
          metric_type: string
          metric_value: number
          model_name: string
          model_version: string
          test_split?: number | null
        }
        Update: {
          created_at?: string
          dataset_size?: number | null
          evaluated_at?: string
          id?: string
          metadata?: Json | null
          metric_type?: string
          metric_value?: number
          model_name?: string
          model_version?: string
          test_split?: number | null
        }
        Relationships: []
      }
      opportunities: {
        Row: {
          auction_end: string | null
          buyer_premium: number | null
          calculation_metadata: Json | null
          confidence_score: number
          created_at: string
          current_bid: number
          doc_fee: number | null
          estimated_sale_price: number
          fees_cost: number | null
          id: string
          is_active: boolean | null
          listing_id: string | null
          location: string | null
          make: string
          market_data: Json | null
          mileage: number | null
          model: string
          potential_profit: number
          profit_margin: number
          risk_score: number
          roi_percentage: number
          score: number | null
          source_site: string
          state: string | null
          status: string | null
          total_cost: number
          transportation_cost: number | null
          updated_at: string
          user_id: string | null
          vin: string | null
          year: number
        }
        Insert: {
          auction_end?: string | null
          buyer_premium?: number | null
          calculation_metadata?: Json | null
          confidence_score: number
          created_at?: string
          current_bid: number
          doc_fee?: number | null
          estimated_sale_price: number
          fees_cost?: number | null
          id?: string
          is_active?: boolean | null
          listing_id?: string | null
          location?: string | null
          make: string
          market_data?: Json | null
          mileage?: number | null
          model: string
          potential_profit: number
          profit_margin: number
          risk_score: number
          roi_percentage: number
          score?: number | null
          source_site: string
          state?: string | null
          status?: string | null
          total_cost: number
          transportation_cost?: number | null
          updated_at?: string
          user_id?: string | null
          vin?: string | null
          year: number
        }
        Update: {
          auction_end?: string | null
          buyer_premium?: number | null
          calculation_metadata?: Json | null
          confidence_score?: number
          created_at?: string
          current_bid?: number
          doc_fee?: number | null
          estimated_sale_price?: number
          fees_cost?: number | null
          id?: string
          is_active?: boolean | null
          listing_id?: string | null
          location?: string | null
          make?: string
          market_data?: Json | null
          mileage?: number | null
          model?: string
          potential_profit?: number
          profit_margin?: number
          risk_score?: number
          roi_percentage?: number
          score?: number | null
          source_site?: string
          state?: string | null
          status?: string | null
          total_cost?: number
          transportation_cost?: number | null
          updated_at?: string
          user_id?: string | null
          vin?: string | null
          year?: number
        }
        Relationships: [
          {
            foreignKeyName: "opportunities_listing_id_fkey"
            columns: ["listing_id"]
            isOneToOne: false
            referencedRelation: "public_listings"
            referencedColumns: ["id"]
          },
        ]
      }
      pipeline_metrics: {
        Row: {
          created_at: string
          id: string
          metric_name: string
          metric_unit: string
          metric_value: number
          tags: Json | null
        }
        Insert: {
          created_at?: string
          id?: string
          metric_name: string
          metric_unit?: string
          metric_value: number
          tags?: Json | null
        }
        Update: {
          created_at?: string
          id?: string
          metric_name?: string
          metric_unit?: string
          metric_value?: number
          tags?: Json | null
        }
        Relationships: []
      }
      profiles: {
        Row: {
          created_at: string
          display_name: string | null
          email: string | null
          id: string
          updated_at: string
          user_id: string
        }
        Insert: {
          created_at?: string
          display_name?: string | null
          email?: string | null
          id?: string
          updated_at?: string
          user_id: string
        }
        Update: {
          created_at?: string
          display_name?: string | null
          email?: string | null
          id?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
      public_listings: {
        Row: {
          auction_end: string | null
          compliance_result: Json | null
          content_hash: string | null
          created_at: string | null
          current_bid: number | null
          description: string | null
          etag: string | null
          id: string
          is_active: boolean | null
          last_modified: string | null
          listing_url: string
          location: string | null
          make: string | null
          mileage: number | null
          model: string | null
          photo_url: string | null
          score_metadata: Json | null
          scored_at: string | null
          scrape_metadata: Json | null
          source_site: string
          state: string | null
          title_status: string | null
          trim: string | null
          updated_at: string | null
          vin: string | null
          year: number | null
        }
        Insert: {
          auction_end?: string | null
          compliance_result?: Json | null
          content_hash?: string | null
          created_at?: string | null
          current_bid?: number | null
          description?: string | null
          etag?: string | null
          id?: string
          is_active?: boolean | null
          last_modified?: string | null
          listing_url: string
          location?: string | null
          make?: string | null
          mileage?: number | null
          model?: string | null
          photo_url?: string | null
          score_metadata?: Json | null
          scored_at?: string | null
          scrape_metadata?: Json | null
          source_site: string
          state?: string | null
          title_status?: string | null
          trim?: string | null
          updated_at?: string | null
          vin?: string | null
          year?: number | null
        }
        Update: {
          auction_end?: string | null
          compliance_result?: Json | null
          content_hash?: string | null
          created_at?: string | null
          current_bid?: number | null
          description?: string | null
          etag?: string | null
          id?: string
          is_active?: boolean | null
          last_modified?: string | null
          listing_url?: string
          location?: string | null
          make?: string | null
          mileage?: number | null
          model?: string | null
          photo_url?: string | null
          score_metadata?: Json | null
          scored_at?: string | null
          scrape_metadata?: Json | null
          source_site?: string
          state?: string | null
          title_status?: string | null
          trim?: string | null
          updated_at?: string | null
          vin?: string | null
          year?: number | null
        }
        Relationships: []
      }
      scoring_jobs: {
        Row: {
          completed_at: string | null
          created_at: string
          error_message: string | null
          id: string
          opportunities_created: number
          processed_listings: number
          progress: number
          started_at: string
          status: string
          total_listings: number
          updated_at: string
          user_id: string | null
        }
        Insert: {
          completed_at?: string | null
          created_at?: string
          error_message?: string | null
          id?: string
          opportunities_created?: number
          processed_listings?: number
          progress?: number
          started_at?: string
          status: string
          total_listings?: number
          updated_at?: string
          user_id?: string | null
        }
        Update: {
          completed_at?: string | null
          created_at?: string
          error_message?: string | null
          id?: string
          opportunities_created?: number
          processed_listings?: number
          progress?: number
          started_at?: string
          status?: string
          total_listings?: number
          updated_at?: string
          user_id?: string | null
        }
        Relationships: []
      }
      scraper_configs: {
        Row: {
          category: string
          created_at: string | null
          headers: Json | null
          id: string
          is_enabled: boolean | null
          max_pages: number | null
          rate_limit_seconds: number | null
          selectors: Json | null
          site_name: string
          site_url: string
          updated_at: string | null
        }
        Insert: {
          category: string
          created_at?: string | null
          headers?: Json | null
          id?: string
          is_enabled?: boolean | null
          max_pages?: number | null
          rate_limit_seconds?: number | null
          selectors?: Json | null
          site_name: string
          site_url: string
          updated_at?: string | null
        }
        Update: {
          category?: string
          created_at?: string | null
          headers?: Json | null
          id?: string
          is_enabled?: boolean | null
          max_pages?: number | null
          rate_limit_seconds?: number | null
          selectors?: Json | null
          site_name?: string
          site_url?: string
          updated_at?: string | null
        }
        Relationships: []
      }
      scraper_sites: {
        Row: {
          base_url: string
          category: string
          enabled: boolean
          id: string
          last_scrape: string | null
          name: string
          priority: number
          status: string
          updated_at: string | null
          vehicles_found: number | null
        }
        Insert: {
          base_url: string
          category: string
          enabled?: boolean
          id: string
          last_scrape?: string | null
          name: string
          priority?: number
          status?: string
          updated_at?: string | null
          vehicles_found?: number | null
        }
        Update: {
          base_url?: string
          category?: string
          enabled?: boolean
          id?: string
          last_scrape?: string | null
          name?: string
          priority?: number
          status?: string
          updated_at?: string | null
          vehicles_found?: number | null
        }
        Relationships: []
      }
      scraping_jobs: {
        Row: {
          completed_at: string | null
          config: Json | null
          error_message: string | null
          id: string
          idempotency_key: string | null
          owner_id: string
          results: Json | null
          sites_targeted: string[] | null
          started_at: string | null
          status: string
        }
        Insert: {
          completed_at?: string | null
          config?: Json | null
          error_message?: string | null
          id: string
          idempotency_key?: string | null
          owner_id: string
          results?: Json | null
          sites_targeted?: string[] | null
          started_at?: string | null
          status: string
        }
        Update: {
          completed_at?: string | null
          config?: Json | null
          error_message?: string | null
          id?: string
          idempotency_key?: string | null
          owner_id?: string
          results?: Json | null
          sites_targeted?: string[] | null
          started_at?: string | null
          status?: string
        }
        Relationships: []
      }
      security_audit_log: {
        Row: {
          action: string
          created_at: string
          details: Json | null
          id: string
          ip_address: unknown | null
          resource: string | null
          status: string
          user_agent: string | null
          user_id: string | null
        }
        Insert: {
          action: string
          created_at?: string
          details?: Json | null
          id?: string
          ip_address?: unknown | null
          resource?: string | null
          status: string
          user_agent?: string | null
          user_id?: string | null
        }
        Update: {
          action?: string
          created_at?: string
          details?: Json | null
          id?: string
          ip_address?: unknown | null
          resource?: string | null
          status?: string
          user_agent?: string | null
          user_id?: string | null
        }
        Relationships: []
      }
      system_logs: {
        Row: {
          context: Json | null
          correlation_id: string | null
          created_at: string | null
          id: string
          level: string
          message: string
          stack_trace: string | null
          timestamp: string | null
        }
        Insert: {
          context?: Json | null
          correlation_id?: string | null
          created_at?: string | null
          id?: string
          level: string
          message: string
          stack_trace?: string | null
          timestamp?: string | null
        }
        Update: {
          context?: Json | null
          correlation_id?: string | null
          created_at?: string | null
          id?: string
          level?: string
          message?: string
          stack_trace?: string | null
          timestamp?: string | null
        }
        Relationships: []
      }
      user_alerts: {
        Row: {
          created_at: string
          dismissed: boolean
          id: string
          message: string
          opportunity_data: Json | null
          opportunity_id: string | null
          priority: string
          title: string
          type: string
          user_id: string
          viewed: boolean
        }
        Insert: {
          created_at?: string
          dismissed?: boolean
          id: string
          message: string
          opportunity_data?: Json | null
          opportunity_id?: string | null
          priority: string
          title: string
          type: string
          user_id: string
          viewed?: boolean
        }
        Update: {
          created_at?: string
          dismissed?: boolean
          id?: string
          message?: string
          opportunity_data?: Json | null
          opportunity_id?: string | null
          priority?: string
          title?: string
          type?: string
          user_id?: string
          viewed?: boolean
        }
        Relationships: []
      }
      user_settings: {
        Row: {
          created_at: string
          email_alerts: boolean | null
          enabled_sites: string[] | null
          id: string
          max_risk_score: number | null
          min_roi_percentage: number | null
          notification_duration: number | null
          notifications_enabled: boolean | null
          preferred_states: string[] | null
          scan_interval: number | null
          scanning_mode: string | null
          sound_enabled: boolean | null
          updated_at: string
          user_id: string
        }
        Insert: {
          created_at?: string
          email_alerts?: boolean | null
          enabled_sites?: string[] | null
          id?: string
          max_risk_score?: number | null
          min_roi_percentage?: number | null
          notification_duration?: number | null
          notifications_enabled?: boolean | null
          preferred_states?: string[] | null
          scan_interval?: number | null
          scanning_mode?: string | null
          sound_enabled?: boolean | null
          updated_at?: string
          user_id: string
        }
        Update: {
          created_at?: string
          email_alerts?: boolean | null
          enabled_sites?: string[] | null
          id?: string
          max_risk_score?: number | null
          min_roi_percentage?: number | null
          notification_duration?: number | null
          notifications_enabled?: boolean | null
          preferred_states?: string[] | null
          scan_interval?: number | null
          scanning_mode?: string | null
          sound_enabled?: boolean | null
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      clean_expired_market_prices: {
        Args: Record<PropertyKey, never>
        Returns: undefined
      }
      log_security_event: {
        Args: {
          p_action: string
          p_details?: Json
          p_resource?: string
          p_status?: string
        }
        Returns: undefined
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const

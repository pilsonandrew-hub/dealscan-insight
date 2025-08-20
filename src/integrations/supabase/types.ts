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
          vin?: string | null
          year?: number
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
          year?: number
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
      public_listings: {
        Row: {
          auction_end: string | null
          created_at: string | null
          current_bid: number | null
          description: string | null
          id: string
          is_active: boolean | null
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
          created_at?: string | null
          current_bid?: number | null
          description?: string | null
          id?: string
          is_active?: boolean | null
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
          created_at?: string | null
          current_bid?: number | null
          description?: string | null
          id?: string
          is_active?: boolean | null
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
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      clean_expired_market_prices: {
        Args: Record<PropertyKey, never>
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
